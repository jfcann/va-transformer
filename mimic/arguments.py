import os
import argparse
from pprint import pprint


class Arguments:
    def __init__(self, mode):
        self.parser = argparse.ArgumentParser(description='chart-transformer')
        self.mode = mode
        self.arguments = None

    def initialise(self):

        # data roots

        self.parser.add_argument('--mimic_root', type=str)
        self.parser.set_defaults(mimic_root='C:/Users/james/Data/MIMIC/mimic-iii-clinical-database-1.4')
        self.parser.add_argument('--data_root', type=str)
        self.parser.set_defaults(data_root='C:/Users/james/Data/MIMIC/mimic-iii-chart-transformers/data')
        self.parser.add_argument('--model_root', type=str)
        self.parser.set_defaults(model_root='C:/Users/james/Data/MIMIC/mimic-iii-chart-transformers/models')
        self.parser.add_argument('--save_root', type=str)
        self.parser.set_defaults(save_root='C:/Users/james/Data/MIMIC/mimic-iii-chart-transformers')
        self.parser.add_argument('--logs_root', type=str)
        self.parser.set_defaults(logs_root='C:/Users/james/Data/MIMIC/mimic-iii-chart-transformers/logs')

        # pretraining constants

        self.parser.add_argument('--num_epochs', type=int, default=3)
        self.parser.add_argument('--batch_size_tr', type=int, default=4)
        self.parser.add_argument('--batch_size_val', type=int, default=4)
        self.parser.add_argument('--learning_rate', type=float, default=1e-4)
        self.parser.add_argument('--validate_every', type=int, default=10)
        self.parser.add_argument('--checkpoint_after', type=int, default=100)
        self.parser.add_argument('--generate_every', type=int, default=20)
        self.parser.add_argument('--generate_length', type=int, default=200)
        self.parser.add_argument('--seq_len', type=int, default=200)
        self.parser.add_argument('--num_batches_tr', type=int, default=2)  # TODO: deprecate
        self.parser.add_argument('--num_batches_val', type=int, default=2)  # TODO: deprecate
        self.parser.add_argument('--grad_accumulate_every', type=int, default=4)  # TODO: deprecate

        # attention specification

        self.parser.add_argument('--attn_dim', type=int, default=100)
        self.parser.add_argument('--attn_depth', type=int, default=3)
        self.parser.add_argument('--attn_heads', type=int, default=4)
        self.parser.add_argument('--attn_dropout', type=float, default=0.)
        self.parser.add_argument('--ff_dropout', type=float, default=0.)

        # general arguments

        self.parser.add_argument('--model_name', type=str, default='test_experiment')
        self.parser.add_argument('--writer_flush_secs', type=int, default=120)
        self.parser.add_argument('--write_embeddings', type=bool, default=True)

        # pretraining specs

        self.parser.add_argument('--test_run', type=bool, default=False)

        # finetuning arguments

        if self.mode == 'finetuning':
            self.parser.add_argument('--ft_batch_size', type=int, default=100)
            self.parser.add_argument('--label_set', type=str, default='readm_30', choices=['readm_30', 'readm_7'])
            self.parser.add_argument('--pretuned_model', type=str, required=True)
            self.parser.add_argument('--weighted_loss', type=bool, default=False)

    def parse(self, verbose=False):
        self.initialise()
        self.arguments = self.parser.parse_args()
        if verbose: pprint(vars(self.arguments), indent=4)
        return self.arguments


class PreprocessingArguments:
    def __init__(self):
        self.parser = argparse.ArgumentParser(description='preprocessor')
        self.arguments = None

    def initialise(self):

        # data roots

        self.parser.add_argument('--mimic_root', type=str)
        self.parser.set_defaults(mimic_root='C:/Users/james/Data/MIMIC/mimic-iii-clinical-database-1.4')
        self.parser.add_argument('--save_root', type=str)
        self.parser.set_defaults(save_root='C:/Users/james/Data/MIMIC/mimic-iii-chart-transformers/test')

        # general arguments

        self.parser.add_argument('--nrows', type=int, default=1000000)

    def parse(self, verbose=False):
        self.initialise()
        self.arguments = self.parser.parse_args()
        if verbose: pprint(vars(self.arguments), indent=4)
        return self.arguments
