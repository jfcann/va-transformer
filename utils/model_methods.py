import tqdm
import torch
import torch.nn.functional as F
from sklearn.metrics import accuracy_score, balanced_accuracy_score, roc_auc_score, \
     mean_squared_error, r2_score, explained_variance_score


class VGLoss:
    def __init__(self, loss, token_loss=None, quant_loss=None):
        self.loss = loss
        self.token_loss = token_loss
        self.quant_loss = quant_loss


class TrainingMethods:
    def __init__(self, model, writer):
        self.model = model
        clip_value = 0.5
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), clip_value)
        self.writer = writer
        self.depth = model.net.attn_layers.depth

    def train(self, train_loader, optimizer, epoch, grad_accum_every=1, gamma=0.5):
        self.model.train()
        cum_loss = cum_token_loss = cum_quant_loss = 0
        for i, X in tqdm.tqdm(enumerate(train_loader), total=len(train_loader),
                              mininterval=0.5, desc=f'epoch {epoch} training'):
            if self.model.with_values:
                token_loss, quant_loss = self.model(X)
                loss = gamma * token_loss + (1 - gamma) * quant_loss
                batch_loss, token_loss, quant_loss = loss.item(), token_loss.item(), quant_loss.item()
                self.writer.add_scalar('batch_loss/train', batch_loss, epoch * len(train_loader) + i)
                cum_token_loss += token_loss
                cum_quant_loss += quant_loss
            else:
                loss = self.model(X)
                token_loss = batch_loss = loss.item()
                self.writer.add_scalar('batch_loss/train', batch_loss, epoch * len(train_loader) + i)
                cum_token_loss += token_loss

            if grad_accum_every > 1:
                if i % grad_accum_every <= (grad_accum_every - 1):
                    loss.backward()
                if i % grad_accum_every == (grad_accum_every - 1):
                    optimizer.step()
                    optimizer.zero_grad()
            else:
                loss.backward()
                optimizer.step()
                optimizer.zero_grad()

            cum_loss += batch_loss

        epoch_loss = cum_loss / len(train_loader)
        epoch_token_loss = cum_token_loss / len(train_loader)
        epoch_quant_loss = cum_quant_loss / len(train_loader)
        epoch_losses = VGLoss(loss=epoch_loss,
                              token_loss=epoch_token_loss,
                              quant_loss=epoch_quant_loss)
        self.writer.add_scalar('epoch_loss/train', epoch_loss, epoch)
        self.writer.add_scalar('epoch_token_loss/train', epoch_token_loss, epoch)
        self.writer.add_scalar('epoch_quantile_loss/train', epoch_quant_loss, epoch)
        print(f'epoch avg train loss: {epoch_loss}',
              f'token | quant loss: {epoch_token_loss} | {epoch_quant_loss}')
        return epoch_losses

    @torch.no_grad()
    def evaluate(self, val_loader, epoch, gamma=0.5):
        self.model.eval()
        cum_loss = cum_token_loss = cum_quant_loss = 0
        for i, X in tqdm.tqdm(enumerate(val_loader), total=len(val_loader),
                              mininterval=0.5, desc=f'epoch {epoch} evaluation'):
            if self.model.quant_guides is None:
                loss = self.model(X)
                token_loss = batch_loss = loss.item()
                cum_loss += batch_loss
                cum_token_loss += token_loss
            else:
                token_loss, quant_loss = self.model(X)
                loss = gamma * token_loss + (1 - gamma) * quant_loss
                cum_loss += loss.item()
                cum_token_loss += token_loss.item()
                cum_quant_loss += quant_loss.item()

        epoch_loss = cum_loss / len(val_loader)
        epoch_token_loss = cum_token_loss / len(val_loader)
        epoch_quant_loss = cum_quant_loss / len(val_loader)
        epoch_losses = VGLoss(loss=epoch_loss,
                              token_loss=epoch_token_loss,
                              quant_loss=epoch_quant_loss)
        self.writer.add_scalar('epoch_loss/val', epoch_loss, epoch)
        self.writer.add_scalar('epoch_token_loss/val', epoch_token_loss, epoch)
        self.writer.add_scalar('epoch_quantile_loss/val', epoch_quant_loss, epoch)
        print(f'epoch avg val loss: {epoch_loss}, token | quant loss: {epoch_token_loss} | {epoch_quant_loss}')
        return epoch_losses

    @torch.no_grad()
    def write_token_emb(self, step, tokens, labeller, seq_len, device):
        self.model.eval()
        x = torch.tensor(tokens, dtype=torch.int)
        z = torch.Tensor().to(device)
        for x_part in torch.split(x, seq_len):
            x_part = x_part.to(device)
            z_part = self.model.net.token_emb(x_part)
            z = torch.cat((z, z_part))
        metadata = [label for label in map(labeller.token2label, x.cpu().numpy())]
        self.writer.add_embedding(z,
                                  metadata=metadata,
                                  global_step=step,
                                  tag='token_embeddings')

    @torch.no_grad()  # dev: should this be an at-the-end eval method?
    def write_output_emb(self, step, tokens, labeller, seq_len, device):
        self.model.eval()
        if labeller.mappings.eos_token is not None:
            pass

    @torch.no_grad()
    def write_g_histograms(self, step):
        self.model.eval()
        to_g_weights = torch.cat([self.model.net.attn_layers.layers[2 * i][1].to_g.weight.detach()
                                  for i in range(self.depth)], dim=1)
        self.writer.add_histogram('to_g_weights', to_g_weights, step)


class FinetuningMethods:
    def __init__(self, model, writer):
        self.model = model
        clip_value = 0.5
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), clip_value)
        self.writer = writer
        self.depth = model.net.attn_layers.depth

    def train(self, train_loader, optimizer, epoch, grad_accum_every=1):
        self.model.train()
        cum_loss = 0
        for i, X in tqdm.tqdm(enumerate(train_loader), total=len(train_loader),
                              mininterval=0.5, desc=f'epoch {epoch} training'):
            loss = self.model(X)

            if grad_accum_every > 1:
                if i % grad_accum_every <= (grad_accum_every - 1):
                    loss.backward()
                if i % grad_accum_every == (grad_accum_every - 1):
                    optimizer.step()
                    optimizer.zero_grad()
            else:
                loss.backward()
                optimizer.step()
                optimizer.zero_grad()

            batch_loss = loss.item()
            optimizer.step()
            optimizer.zero_grad()
            self.writer.add_scalar('batch_loss/train', batch_loss, epoch * len(train_loader) + i)
            cum_loss += batch_loss

        epoch_loss = cum_loss / len(train_loader)
        self.writer.add_scalar('epoch_loss/train', epoch_loss, epoch)
        print(f'epoch avg train loss: {epoch_loss}')
        return epoch_loss

    @torch.no_grad()
    def evaluate(self, val_loader, epoch):
        self.model.eval()
        cum_loss = 0
        for i, X in tqdm.tqdm(enumerate(val_loader), total=len(val_loader),
                              mininterval=0.5, desc=f'epoch {epoch} evaluation'):
            loss = self.model(X)
            cum_loss += loss.item()

        epoch_loss = cum_loss / len(val_loader)
        self.writer.add_scalar('epoch_loss/val', epoch_loss, epoch)
        print(f'epoch avg val loss: {epoch_loss}')
        return epoch_loss

    @torch.no_grad()
    def predict(self, data_loader, epoch, device, prefix="val", clf_or_reg='clf'):
        self.model.eval()
        y_score = torch.tensor([]).to(device)
        y_true = torch.tensor([]).to(device)
        for i, X in tqdm.tqdm(enumerate(data_loader), total=len(data_loader),
                              mininterval=0.5, desc=f'epoch {epoch} prediction'):
            targets = X[-1]
            y_true = torch.cat((y_true, targets))
            if clf_or_reg == 'clf':
                logits = self.model(X, predict=True)
                y_score = torch.cat((y_score, F.softmax(logits, dim=1)))
            elif clf_or_reg == 'reg':
                preds = self.model(X, predict=True)
                y_score = torch.cat((y_score, preds))

        y_true = y_true.cpu()
        y_score = y_score.cpu()

        metrics = {}
        if clf_or_reg == 'clf':
            acc = accuracy_score(y_true, torch.argmax(y_score, dim=1), normalize=True)
            bal_acc = balanced_accuracy_score(y_true, torch.argmax(y_score, dim=1))
            roc_auc = roc_auc_score(y_true, y_score[:, 1])
            metrics = {'acc': acc, 'bal_acc': bal_acc, 'roc_auc': roc_auc}
            self.writer.add_scalar(prefix + '/acc', acc, epoch)
            self.writer.add_scalar(prefix + '/bal_acc', bal_acc, epoch)
            self.writer.add_scalar(prefix + '/roc_auc', roc_auc, epoch)
            self.writer.add_pr_curve(prefix + '/pr_curve', y_true, y_score[:, 1], epoch)
            print(f'epoch {prefix}/roc_auc = {roc_auc}, {prefix}/bal_acc = {bal_acc}, {prefix}/acc = {acc}')
        elif clf_or_reg == 'reg':
            mse = mean_squared_error(y_true, y_score)
            r2 = r2_score(y_true, y_score)
            exp_var = explained_variance_score(y_true, y_score)
            metrics = {"mse": mse, "r2": r2, "exp_var": exp_var}
            self.writer.add_scalar(prefix + '/mse', mse, epoch)
            self.writer.add_scalar(prefix + '/r2', r2, epoch)
            self.writer.add_scalar(prefix + '/exp_var', exp_var, epoch)
            print(f'epoch {prefix}/mse = {mse}, {prefix}/r2 = {r2}, {prefix}/exp_var = {exp_var}')

        return y_score, y_true, metrics

    @torch.no_grad()
    def write_embeddings(self, step, mappings, labeller, seq_len, device):
        self.model.eval()
        tokens = list(mappings.top_n_train_tokens(2000).keys())
        x = torch.tensor(tokens, dtype=torch.int)
        z = torch.Tensor().to(device)
        for x_part in torch.split(x, seq_len):
            x_part = x_part.to(device)
            z_part = self.model.net.token_emb(x_part)
            z = torch.cat((z, z_part))
        metadata = [label for label in map(labeller.token2label, x.cpu().numpy())]
        self.writer.add_embedding(z,
                                  metadata=metadata,
                                  global_step=step,
                                  tag='token_embeddings')

    @torch.no_grad()
    def write_g_histograms(self, step):
        self.model.eval()
        to_g_weights = torch.cat([self.model.net.attn_layers.layers[2 * i][1].to_g.weight.detach()
                                  for i in range(self.depth)], dim=1)
        self.writer.add_histogram('to_g_weights', to_g_weights, step)


class BaselineMethods:
    def __init__(self, model, writer):
        self.model = model
        self.writer = writer

    def train(self, train_loader, optimizer, epoch, grad_accum_every=1):
        self.model.train()
        cum_loss = 0
        for i, X in tqdm.tqdm(enumerate(train_loader), total=len(train_loader),
                              mininterval=0.5, desc=f'epoch {epoch} training'):
            loss = self.model(X)

            if grad_accum_every > 1:
                if i % grad_accum_every <= (grad_accum_every - 1):
                    loss.backward()
                if i % grad_accum_every == (grad_accum_every - 1):
                    optimizer.step()
                    optimizer.zero_grad()
            else:
                loss.backward()
                optimizer.step()
                optimizer.zero_grad()

            batch_loss = loss.item()
            optimizer.step()
            optimizer.zero_grad()
            self.writer.add_scalar('batch_loss/train', batch_loss, epoch * len(train_loader) + i)
            cum_loss += batch_loss

        epoch_loss = cum_loss / len(train_loader)
        self.writer.add_scalar('epoch_loss/train', epoch_loss, epoch)
        print(f'epoch avg train loss: {epoch_loss}')
        return epoch_loss

    @torch.no_grad()
    def evaluate(self, val_loader, epoch):
        self.model.eval()
        cum_loss = 0
        for i, X in tqdm.tqdm(enumerate(val_loader), total=len(val_loader),
                              mininterval=0.5, desc=f'epoch {epoch} evaluation'):
            loss = self.model(X)
            cum_loss += loss.item()

        epoch_loss = cum_loss / len(val_loader)
        self.writer.add_scalar('epoch_loss/val', epoch_loss, epoch)
        print(f'epoch avg val loss: {epoch_loss}')
        return epoch_loss

    @torch.no_grad()
    def predict(self, data_loader, epoch, device, prefix="val", clf_or_reg='clf'):
        self.model.eval()
        y_score = torch.tensor([]).to(device)
        y_true = torch.tensor([]).to(device)
        for i, X in tqdm.tqdm(enumerate(data_loader), total=len(data_loader),
                              mininterval=0.5, desc=f'epoch {epoch} prediction'):
            targets = X[-1]
            y_true = torch.cat((y_true, targets))
            if clf_or_reg == 'clf':
                logits = self.model(X, predict=True)
                y_score = torch.cat((y_score, F.softmax(logits, dim=1)))
            elif clf_or_reg == 'reg':
                preds = self.model(X, predict=True)
                y_score = torch.cat((y_score, preds))

        y_true = y_true.cpu()
        y_score = y_score.cpu()

        metrics = {}
        if clf_or_reg == 'clf':
            acc = accuracy_score(y_true, torch.argmax(y_score, dim=1), normalize=True)
            bal_acc = balanced_accuracy_score(y_true, torch.argmax(y_score, dim=1))
            roc_auc = roc_auc_score(y_true, y_score[:, 1])
            metrics = {'acc': acc, 'bal_acc': bal_acc, 'roc_auc': roc_auc}
            self.writer.add_scalar(prefix + '/acc', acc, epoch)
            self.writer.add_scalar(prefix + '/bal_acc', bal_acc, epoch)
            self.writer.add_scalar(prefix + '/roc_auc', roc_auc, epoch)
            self.writer.add_pr_curve(prefix + '/pr_curve', y_true, y_score[:, 1], epoch)
            print(f'epoch {prefix}/roc_auc = {roc_auc}, {prefix}/bal_acc = {bal_acc}, {prefix}/acc = {acc}')
        elif clf_or_reg == 'reg':
            mse = mean_squared_error(y_true, y_score)
            r2 = r2_score(y_true, y_score)
            exp_var = explained_variance_score(y_true, y_score)
            metrics = {"mse": mse, "r2": r2, "exp_var": exp_var}
            self.writer.add_scalar(prefix + '/mse', mse, epoch)
            self.writer.add_scalar(prefix + '/r2', r2, epoch)
            self.writer.add_scalar(prefix + '/exp_var', exp_var, epoch)
            print(f'epoch {prefix}/mse = {mse}, {prefix}/r2 = {r2}, {prefix}/exp_var = {exp_var}')

        return y_score, y_true, metrics


"""
    @torch.no_grad()
    def predict(self, data_loader, epoch, device, prefix="val"):
        self.model.eval()
        y_score = torch.tensor([]).to(device)
        y_true = torch.tensor([]).to(device)
        for i, X in tqdm.tqdm(enumerate(data_loader), total=len(data_loader),
                              mininterval=0.5, desc=f'epoch {epoch} prediction'
                              ):
            labels = X[-1]
            y_true = torch.cat((y_true, labels))
            logits = self.model(X, predict=True)
            y_score = torch.cat((y_score, F.softmax(logits, dim=1)))
            
            
            if clf_or_reg == 'clf':
                logits = self.model(X, predict=True)
                y_score = torch.cat((y_score, F.softmax(logits, dim=1)))
            elif clf_or_reg == 'reg':
                preds = self.model(X, predict=True)
                y_score = torch.cat((y_score, preds))
                
        y_true = y_true.cpu()
        y_score = y_score.cpu()

        acc = accuracy_score(y_true, torch.argmax(y_score, dim=1), normalize=True)
        bal_acc = balanced_accuracy_score(y_true, torch.argmax(y_score, dim=1))
        roc_auc = roc_auc_score(y_true, y_score[:, 1])

        if self.writer is not None:
            self.writer.add_scalar(prefix + '/acc', acc, epoch)
            self.writer.add_scalar(prefix + '/bal_acc', bal_acc, epoch)
            self.writer.add_scalar(prefix + '/roc_auc', roc_auc, epoch)
            self.writer.add_pr_curve(prefix + '/pr_curve', y_true, y_score[:, 1], epoch)
        print(f'epoch {prefix}/roc_auc = {roc_auc}, {prefix}/bal_acc = {bal_acc}, {prefix}/acc = {acc}')
        return y_score[:, 1], y_true, acc, bal_acc, roc_auc
"""