# Requriments - transformers, tokenizers
# Right now, the Smiles Tokenizer uses an exiesting vocab file from rxnfp that is fairly comprehensive and from the USPTO dataset.
# The vocab may be expanded in the near future

import collections
import logging
import os
import re
import numpy as np
import pkg_resources
import typing
from typing import List
from transformers import BertTokenizer
from logging import getLogger

logger = getLogger(__name__)
"""
SMI_REGEX_PATTERN: str
    SMILES regex pattern for tokenization. Designed by Schwaller et. al.

References

.. [1]  Philippe Schwaller, Teodoro Laino, Théophile Gaudin, Peter Bolgar, Christopher A. Hunter, Costas Bekas, and Alpha A. Lee
        ACS Central Science 2019 5 (9): Molecular Transformer: A Model for Uncertainty-Calibrated Chemical Reaction Prediction
        1572-1583 DOI: 10.1021/acscentsci.9b00576

"""

SMI_REGEX_PATTERN = r"""(\[[^\]]+]|Br?|Cl?|N|O|S|P|F|I|b|c|n|o|s|p|\(|\)|\.|=|
#|-|\+|\\|\/|:|~|@|\?|>>?|\*|\$|\%[0-9]{2}|[0-9])"""

# add vocab_file dict
VOCAB_FILES_NAMES = {"vocab_file": "vocab.txt"}


def get_default_tokenizer():
  default_vocab_path = (pkg_resources.resource_filename("deepchem",
                                                        "feat/tests/vocab.txt"))
  return SmilesTokenizer(default_vocab_path)


class SmilesTokenizer(BertTokenizer):
  """
    Creates the SmilesTokenizer class. The tokenizer heavily inherits from the BertTokenizer
    implementation found in Huggingface's transformers library. It runs a WordPiece tokenization
    algorithm over SMILES strings using the tokenisation SMILES regex developed by Schwaller et. al.

    Please see https://github.com/huggingface/transformers
    and https://github.com/rxn4chemistry/rxnfp for more details.

    Examples
    --------

    >>> from deepchem.feat.smiles_tokenizer import SmilesTokenizer

    >>> current_dir = os.path.dirname(os.path.realpath(__file__))
    >>> vocab_path = os.path.join(current_dir, 'tests/data', 'vocab.txt')

    >>> tokenizer = SmilesTokenizer(vocab_path)
    >>> print(tokenizer.encode("CCC(CC)COC(=O)[C@H](C)N[P@](=O)(OC[C@H]1O[C@](C#N)([C@H](O)[C@@H]1O)C1=CC=C2N1N=CN=C2N)OC1=CC=CC=C1"))
    [12, 16, 16, 16, 17, 16, 16, 18, 16, 19, 16, 17, 22, 19, 18, 33, 17, 16, 18, 23, 181, 17, 22, 19, 18, 17, 19, 16, 33, 20, 19, 55, 17, 16, 23, 18, 17, 33, 17, 19, 18, 35, 20, 19, 18, 16, 20, 22, 16, 16, 22, 16, 21, 23, 20, 23, 22, 16, 23, 22, 16, 21, 23, 18, 19, 16, 20, 22, 16, 16, 22, 16, 16, 22, 16, 20, 13]


    References
    ----------
    .. [1]  Schwaller, Philippe; Probst, Daniel; Vaucher, Alain C.; Nair, Vishnu H; Kreutter, David;
            Laino, Teodoro; et al. (2019): Mapping the Space of Chemical Reactions using Attention-Based Neural
            Networks. ChemRxiv. Preprint. https://doi.org/10.26434/chemrxiv.9897365.v3
    Notes
    ----
    This class requires huggingface's transformers and tokenizers libraries to be installed.

    """
  vocab_files_names = VOCAB_FILES_NAMES

  def __init__(
      self,
      vocab_file: str = '',
      # unk_token="[UNK]",
      # sep_token="[SEP]",
      # pad_token="[PAD]",
      # cls_token="[CLS]",
      # mask_token="[MASK]",
      **kwargs):
    """Constructs a SmilesTokenizer.

        Parameters
        ----------
        vocab_file: str
            Path to a SMILES character per line vocabulary file.
            Default vocab file is found in deepchem/feat/tests/data/vocab.txt
        """

    super().__init__(vocab_file, **kwargs)
    # take into account special tokens in max length
    self.max_len_single_sentence = self.max_len - 2
    self.max_len_sentences_pair = self.max_len - 3

    if not os.path.isfile(vocab_file):
      raise ValueError(
          "Can't find a vocab file at path '{}'.".format(vocab_file))
    self.vocab = load_vocab(vocab_file)
    self.highest_unused_index = max(
        [i for i, v in enumerate(self.vocab.keys()) if v.startswith("[unused")])
    self.ids_to_tokens = collections.OrderedDict(
        [(ids, tok) for tok, ids in self.vocab.items()])
    self.basic_tokenizer = BasicSmilesTokenizer()
    self.init_kwargs["max_len"] = self.max_len

  @property
  def vocab_size(self):
    return len(self.vocab)

  @property
  def vocab_list(self):
    return list(self.vocab.keys())

  def _tokenize(self, text: str):
    """
        Tokenize a string into a list of tokens.

        Parameters
        ----------
        text: str
            Input string sequence to be tokenized.
        """

    split_tokens = [token for token in self.basic_tokenizer.tokenize(text)]
    return split_tokens

  def _convert_token_to_id(self, token):
    """
        Converts a token (str/unicode) in an id using the vocab.

        Parameters
        ----------
        token: str
            String token from a larger sequence to be converted to a numerical id.
        """

    return self.vocab.get(token, self.vocab.get(self.unk_token))

  def _convert_id_to_token(self, index):
    """
        Converts an index (integer) in a token (string/unicode) using the vocab.

        Parameters
        ----------
        index: int
            Integer index to be converted back to a string-based token as part of a larger sequence.
        """

    return self.ids_to_tokens.get(index, self.unk_token)

  def convert_tokens_to_string(self, tokens: List[str]):
    """ Converts a sequence of tokens (string) in a single string.

        Parameters
        ----------
        tokens: List[str]
            List of tokens for a given string sequence.

        Returns
        -------
        out_string: str
            Single string from combined tokens.
        """

    out_string: str = " ".join(tokens).replace(" ##", "").strip()
    return out_string

  def add_special_tokens_ids_single_sequence(self, token_ids: List[int]):
    """
        Adds special tokens to the a sequence for sequence classification tasks.
        A BERT sequence has the following format: [CLS] X [SEP]

        Parameters
        ----------

        token_ids: list[int]
            list of tokenized input ids. Can be obtained using the encode or encode_plus methods.
        """

    return [self.cls_token_id] + token_ids + [self.sep_token_id]

  def add_special_tokens_single_sequence(self, tokens: List[str]):
    """
        Adds special tokens to the a sequence for sequence classification tasks.
        A BERT sequence has the following format: [CLS] X [SEP]

        Parameters
        ----------
        tokens: List[str]
            List of tokens for a given string sequence.

        """
    return [self.cls_token] + tokens + [self.sep_token]

  def add_special_tokens_ids_sequence_pair(self, token_ids_0: List[int],
                                           token_ids_1: List[int]) -> List[int]:
    """
        Adds special tokens to a sequence pair for sequence classification tasks.
        A BERT sequence pair has the following format: [CLS] A [SEP] B [SEP]

        Parameters
        ----------
        token_ids_0: List[int]
            List of ids for the first string sequence in the sequence pair (A).

        token_ids_1: List[int]
            List of tokens for the second string sequence in the sequence pair (B).
        """

    sep = [self.sep_token_id]
    cls = [self.cls_token_id]

    return cls + token_ids_0 + sep + token_ids_1 + sep

  def add_padding_tokens(self,
                         token_ids: List[int],
                         length: int,
                         right: bool = True) -> List[int]:
    """
        Adds padding tokens to return a sequence of length max_length.
        By default padding tokens are added to the right of the sequence.

        Parameters
        ----------
        token_ids: list[int]
            list of tokenized input ids. Can be obtained using the encode or encode_plus methods.

        length: int

        right: bool (True by default)

        Returns
        ----------
        token_ids :
            list of tokenized input ids. Can be obtained using the encode or encode_plus methods.

        padding: int
            Integer to be added as padding token

        """
    padding = [self.pad_token_id] * (length - len(token_ids))

    if right:
      return token_ids + padding
    else:
      return padding + token_ids

  def save_vocabulary(
      self, vocab_path: str
  ):  # -> tuple[str]: doctest issue raised with this return type annotation
    """
        Save the tokenizer vocabulary to a file.

        Parameters
        ----------
        vocab_path: obj: str
            The directory in which to save the SMILES character per line vocabulary file.
            Default vocab file is found in deepchem/feat/tests/data/vocab.txt

        Returns
        ----------
        vocab_file: :obj:`Tuple(str)`:
            Paths to the files saved.
            typle with string to a SMILES character per line vocabulary file.
            Default vocab file is found in deepchem/feat/tests/data/vocab.txt

        """
    index = 0
    if os.path.isdir(vocab_path):
      vocab_file = os.path.join(vocab_path, VOCAB_FILES_NAMES["vocab_file"])
    else:
      vocab_file = vocab_path
    with open(vocab_file, "w", encoding="utf-8") as writer:
      for token, token_index in sorted(
          self.vocab.items(), key=lambda kv: kv[1]):
        if index != token_index:
          logger.warning(
              "Saving vocabulary to {}: vocabulary indices are not consecutive."
              " Please check that the vocabulary is not corrupted!".format(
                  vocab_file))
          index = token_index
        writer.write(token + "\n")
        index += 1
    return (vocab_file,)


class BasicSmilesTokenizer(object):
  """

    Run basic SMILES tokenization using a regex pattern developed by Schwaller et. al. This tokenizer is to be used
    when a tokenizer that does not require the transformers library by HuggingFace is required.

    Examples
    --------
    >>> from deepchem.feat.smiles_tokenizer import BasicSmilesTokenizer

    >>> tokenizer = BasicSmilesTokenizer()
    >>> print(tokenizer.tokenize("CCC(CC)COC(=O)[C@H](C)N[P@](=O)(OC[C@H]1O[C@](C#N)([C@H](O)[C@@H]1O)C1=CC=C2N1N=CN=C2N)OC1=CC=CC=C1"))
    ['C', 'C', 'C', '(', 'C', 'C', ')', 'C', 'O', 'C', '(', '=', 'O', ')', '[C@H]', '(', 'C', ')', 'N', '[P@]', '(', '=', 'O', ')', '(', 'O', 'C', '[C@H]', '1', 'O', '[C@]', '(', 'C', 'N', ')', '(', '[C@H]', '(', 'O', ')', '[C@@H]', '1', 'O', ')', 'C', '1', '=', 'C', 'C', '=', 'C', '2', 'N', '1', 'N', '=', 'C', 'N', '=', 'C', '2', 'N', ')', 'O', 'C', '1', '=', 'C', 'C', '=', 'C', 'C', '=', 'C', '1']


    References
    ----------
    .. [1]  Philippe Schwaller, Teodoro Laino, Théophile Gaudin, Peter Bolgar, Christopher A. Hunter, Costas Bekas, and Alpha A. Lee
            ACS Central Science 2019 5 (9): Molecular Transformer: A Model for Uncertainty-Calibrated Chemical Reaction Prediction
            1572-1583 DOI: 10.1021/acscentsci.9b00576

    """

  def __init__(self, regex_pattern: str = SMI_REGEX_PATTERN):
    """ Constructs a BasicSMILESTokenizer.
        Parameters
        ----------

        regex: string
            SMILES token regex

        """
    self.regex_pattern = regex_pattern
    self.regex = re.compile(self.regex_pattern)

  def tokenize(self, text):
    """ Basic Tokenization of a SMILES.
        """
    tokens = [token for token in self.regex.findall(text)]
    return tokens


def load_vocab(vocab_file):
  """Loads a vocabulary file into a dictionary."""
  vocab = collections.OrderedDict()
  with open(vocab_file, "r", encoding="utf-8") as reader:
    tokens = reader.readlines()
  for index, token in enumerate(tokens):
    token = token.rstrip("\n")
    vocab[token] = index
  return vocab
