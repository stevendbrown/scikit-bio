# ----------------------------------------------------------------------------
# Copyright (c) 2013--, scikit-bio development team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
# ----------------------------------------------------------------------------

from __future__ import absolute_import, division, print_function

from unittest import TestCase, main
import warnings

import six
import numpy as np

from skbio import Sequence, Protein, DNA, RNA, TabularMSA
from skbio.alignment import (
    global_pairwise_align_protein, local_pairwise_align_protein,
    global_pairwise_align_nucleotide, local_pairwise_align_nucleotide,
    make_identity_substitution_matrix, local_pairwise_align,
    global_pairwise_align)
from skbio.alignment._pairwise import (
    _init_matrices_sw, _init_matrices_nw,
    _compute_score_and_traceback_matrices, _traceback, _first_largest,
    _compute_substitution_score)
from skbio.sequence import GrammaredSequence
from skbio.util._decorator import classproperty, overrides


class CustomSequence(GrammaredSequence):
    @classproperty
    @overrides(GrammaredSequence)
    def gap_chars(cls):
        return set('^$')

    @classproperty
    @overrides(GrammaredSequence)
    def default_gap_char(cls):
        return '^'

    @classproperty
    @overrides(GrammaredSequence)
    def nondegenerate_chars(cls):
        return set('WXYZ')

    @classproperty
    @overrides(GrammaredSequence)
    def degenerate_map(cls):
        return {}


class PairwiseAlignmentTests(TestCase):
    """
        Note: In the high-level tests, the expected results were derived with
        assistance from the EMBOSS web server:
        http://www.ebi.ac.uk/Tools/psa/emboss_needle/
        http://www.ebi.ac.uk/Tools/psa/emboss_water/
        In some cases, placement of non-gap characters surrounded by gap
        characters are slighly different between scikit-bio and the EMBOSS
        server. These differences arise from arbitrary implementation
        differences, and always result in the same score (which tells us that
        the alignments are equivalent). In cases where the expected results
        included here differ from those generated by the EMBOSS server, I note
        the EMBOSS result as a comment below the expected value.

    """

    def setUp(self):
        """Ignore warnings during tests."""
        warnings.simplefilter("ignore")

    def tearDown(self):
        """Clear the list of warning filters, so that no filters are active."""
        warnings.resetwarnings()

    def test_make_identity_substitution_matrix(self):
        expected = {'A': {'A':  1, 'C': -2, 'G': -2, 'T': -2, 'U': -2},
                    'C': {'A': -2, 'C':  1, 'G': -2, 'T': -2, 'U': -2},
                    'G': {'A': -2, 'C': -2, 'G':  1, 'T': -2, 'U': -2},
                    'T': {'A': -2, 'C': -2, 'G': -2, 'T':  1, 'U': -2},
                    'U': {'A': -2, 'C': -2, 'G': -2, 'T': -2, 'U':  1}}
        self.assertEqual(make_identity_substitution_matrix(1, -2), expected)

        expected = {'A': {'A':  5, 'C': -4, 'G': -4, 'T': -4, 'U': -4},
                    'C': {'A': -4, 'C':  5, 'G': -4, 'T': -4, 'U': -4},
                    'G': {'A': -4, 'C': -4, 'G':  5, 'T': -4, 'U': -4},
                    'T': {'A': -4, 'C': -4, 'G': -4, 'T':  5, 'U': -4},
                    'U': {'A': -4, 'C': -4, 'G': -4, 'T': -4, 'U':  5}}
        self.assertEqual(make_identity_substitution_matrix(5, -4), expected)

    def test_global_pairwise_align_custom_alphabet(self):
        custom_substitution_matrix = make_identity_substitution_matrix(
            1, -1, alphabet=CustomSequence.nondegenerate_chars)

        custom_msa, custom_score, custom_start_end = global_pairwise_align(
            CustomSequence("WXYZ"), CustomSequence("WXYYZZ"),
            10.0, 5.0, custom_substitution_matrix)

        # Expected values computed by running an equivalent alignment using the
        # DNA alphabet with the following mapping:
        #
        #     W X Y Z
        #     | | | |
        #     A C G T
        #
        self.assertEqual(custom_msa, TabularMSA([CustomSequence('WXYZ^^'),
                                                 CustomSequence('WXYYZZ')]))
        self.assertEqual(custom_score, 2.0)
        self.assertEqual(custom_start_end, [(0, 3), (0, 5)])

    def test_local_pairwise_align_custom_alphabet(self):
        custom_substitution_matrix = make_identity_substitution_matrix(
            5, -4, alphabet=CustomSequence.nondegenerate_chars)

        custom_msa, custom_score, custom_start_end = local_pairwise_align(
            CustomSequence("YWXXZZYWXXWYYZWXX"),
            CustomSequence("YWWXZZZYWXYZWWX"), 5.0, 0.5,
            custom_substitution_matrix)

        # Expected values computed by running an equivalent alignment using the
        # DNA alphabet with the following mapping:
        #
        #     W X Y Z
        #     | | | |
        #     A C G T
        #
        self.assertEqual(
            custom_msa,
            TabularMSA([CustomSequence('WXXZZYWXXWYYZWXX'),
                        CustomSequence('WXZZZYWX^^^YZWWX')]))
        self.assertEqual(custom_score, 41.0)
        self.assertEqual(custom_start_end, [(1, 16), (2, 14)])

    def test_global_pairwise_align_invalid_type(self):
        with six.assertRaisesRegex(self, TypeError,
                                   "GrammaredSequence.*"
                                   "TabularMSA.*'Sequence'"):
            global_pairwise_align(DNA('ACGT'), Sequence('ACGT'), 1.0, 1.0, {})

    def test_global_pairwise_align_dtype_mismatch(self):
        with six.assertRaisesRegex(self, TypeError,
                                   "same dtype: 'DNA' != 'RNA'"):
            global_pairwise_align(DNA('ACGT'), TabularMSA([RNA('ACGU')]),
                                  1.0, 1.0, {})

        with six.assertRaisesRegex(self, TypeError,
                                   "same dtype: 'DNA' != 'RNA'"):
            global_pairwise_align(TabularMSA([DNA('ACGT')]),
                                  TabularMSA([RNA('ACGU')]),
                                  1.0, 1.0, {})

    def test_global_pairwise_align_protein(self):
        obs_msa, obs_score, obs_start_end = global_pairwise_align_protein(
            Protein("HEAGAWGHEE"), Protein("PAWHEAE"), gap_open_penalty=10.,
            gap_extend_penalty=5.)

        self.assertEqual(obs_msa, TabularMSA([Protein("HEAGAWGHEE-"),
                                              Protein("---PAW-HEAE")]))
        self.assertEqual(obs_score, 23.0)
        self.assertEqual(obs_start_end, [(0, 9), (0, 6)])

        # EMBOSS result: P---AW-HEAE
        obs_msa, obs_score, obs_start_end = global_pairwise_align_protein(
            Protein("HEAGAWGHEE"), Protein("PAWHEAE"), gap_open_penalty=5.,
            gap_extend_penalty=0.5)

        self.assertEqual(obs_msa, TabularMSA([Protein("HEAGAWGHE-E"),
                                              Protein("---PAW-HEAE")]))
        self.assertEqual(obs_score, 30.0)
        self.assertEqual(obs_start_end, [(0, 9), (0, 6)])

        # Protein sequences with metadata
        obs_msa, obs_score, obs_start_end = global_pairwise_align_protein(
            Protein("HEAGAWGHEE", metadata={'id': "s1"}),
            Protein("PAWHEAE", metadata={'id': "s2"}),
            gap_open_penalty=10., gap_extend_penalty=5.)

        self.assertEqual(obs_msa, TabularMSA([Protein("HEAGAWGHEE-"),
                                              Protein("---PAW-HEAE")]))
        self.assertEqual(obs_score, 23.0)
        self.assertEqual(obs_start_end, [(0, 9), (0, 6)])

        # One TabularMSA and one Protein as input
        obs_msa, obs_score, obs_start_end = global_pairwise_align_protein(
            TabularMSA([Protein("HEAGAWGHEE", metadata={'id': "s1"})]),
            Protein("PAWHEAE", metadata={'id': "s2"}),
            gap_open_penalty=10., gap_extend_penalty=5.)

        self.assertEqual(obs_msa, TabularMSA([Protein("HEAGAWGHEE-"),
                                              Protein("---PAW-HEAE")]))
        self.assertEqual(obs_score, 23.0)
        self.assertEqual(obs_start_end, [(0, 9), (0, 6)])

        # One single-sequence alignment as input and one double-sequence
        # alignment as input. Score confirmed manually.
        obs_msa, obs_score, obs_start_end = global_pairwise_align_protein(
            TabularMSA([Protein("HEAGAWGHEE", metadata={'id': "s1"}),
                        Protein("HDAGAWGHDE", metadata={'id': "s2"})]),
            TabularMSA([Protein("PAWHEAE", metadata={'id': "s3"})]),
            gap_open_penalty=10., gap_extend_penalty=5.)

        self.assertEqual(obs_msa, TabularMSA([Protein("HEAGAWGHEE-"),
                                              Protein("HDAGAWGHDE-"),
                                              Protein("---PAW-HEAE")]))
        self.assertEqual(obs_score, 21.0)
        self.assertEqual(obs_start_end, [(0, 9), (0, 6)])

        # TypeError on invalid input
        self.assertRaises(TypeError, global_pairwise_align_protein,
                          42, Protein("HEAGAWGHEE"))
        self.assertRaises(TypeError, global_pairwise_align_protein,
                          Protein("HEAGAWGHEE"), 42)

    def test_global_pairwise_align_protein_invalid_dtype(self):
        with six.assertRaisesRegex(self, TypeError,
                                   "TabularMSA with Protein dtype.*dtype "
                                   "'DNA'"):
            global_pairwise_align_protein(TabularMSA([Protein('PAW')]),
                                          TabularMSA([DNA('ACGT')]))

    def test_global_pairwise_align_protein_penalize_terminal_gaps(self):
        obs_msa, obs_score, obs_start_end = global_pairwise_align_protein(
            Protein("HEAGAWGHEE"), Protein("PAWHEAE"), gap_open_penalty=10.,
            gap_extend_penalty=5., penalize_terminal_gaps=True)

        self.assertEqual(obs_msa, TabularMSA([Protein("HEAGAWGHEE"),
                                              Protein("---PAWHEAE")]))
        self.assertEqual(obs_score, 1.0)
        self.assertEqual(obs_start_end, [(0, 9), (0, 6)])

    def test_global_pairwise_align_nucleotide_penalize_terminal_gaps(self):
        # in these tests one sequence is about 3x the length of the other.
        # we toggle penalize_terminal_gaps to confirm that it results in
        # different alignments and alignment scores.
        seq1 = DNA("ACCGTGGACCGTTAGGATTGGACCCAAGGTTG")
        seq2 = DNA("T"*25 + "ACCGTGGACCGTAGGATTGGACCAAGGTTA" + "A"*25)

        obs_msa, obs_score, obs_start_end = global_pairwise_align_nucleotide(
            seq1, seq2, gap_open_penalty=5., gap_extend_penalty=0.5,
            match_score=5, mismatch_score=-4, penalize_terminal_gaps=False)

        self.assertEqual(
            obs_msa,
            TabularMSA([DNA("-------------------------ACCGTGGACCGTTAGGA"
                            "TTGGACCCAAGGTTG-------------------------"),
                        DNA("TTTTTTTTTTTTTTTTTTTTTTTTTACCGTGGACCGT-AGGA"
                            "TTGGACC-AAGGTTAAAAAAAAAAAAAAAAAAAAAAAAAA")]))
        self.assertEqual(obs_score, 131.0)

        obs_msa, obs_score, obs_start_end = global_pairwise_align_nucleotide(
            seq1, seq2, gap_open_penalty=5., gap_extend_penalty=0.5,
            match_score=5, mismatch_score=-4, penalize_terminal_gaps=True)

        self.assertEqual(
            obs_msa,
            TabularMSA([DNA("-------------------------ACCGTGGACCGTTAGGA"
                            "TTGGACCCAAGGTT-------------------------G"),
                        DNA("TTTTTTTTTTTTTTTTTTTTTTTTTACCGTGGACCGT-AGGA"
                            "TTGGACC-AAGGTTAAAAAAAAAAAAAAAAAAAAAAAAAA")]))
        self.assertEqual(obs_score, 97.0)

    def test_local_pairwise_align_protein(self):
        obs_msa, obs_score, obs_start_end = local_pairwise_align_protein(
            Protein("HEAGAWGHEE"), Protein("PAWHEAE"), gap_open_penalty=10.,
            gap_extend_penalty=5.)

        self.assertEqual(obs_msa, TabularMSA([Protein("AWGHE"),
                                              Protein("AW-HE")]))
        self.assertEqual(obs_score, 26.0)
        self.assertEqual(obs_start_end, [(4, 8), (1, 4)])

        obs_msa, obs_score, obs_start_end = local_pairwise_align_protein(
            Protein("HEAGAWGHEE"), Protein("PAWHEAE"), gap_open_penalty=5.,
            gap_extend_penalty=0.5)

        self.assertEqual(obs_msa, TabularMSA([Protein("AWGHE-E"),
                                              Protein("AW-HEAE")]))
        self.assertEqual(obs_score, 32.0)
        self.assertEqual(obs_start_end, [(4, 9), (1, 6)])

        # Protein sequences with metadata
        obs_msa, obs_score, obs_start_end = local_pairwise_align_protein(
            Protein("HEAGAWGHEE", metadata={'id': "s1"}),
            Protein("PAWHEAE", metadata={'id': "s2"}),
            gap_open_penalty=10., gap_extend_penalty=5.)

        self.assertEqual(obs_msa, TabularMSA([Protein("AWGHE"),
                                              Protein("AW-HE")]))
        self.assertEqual(obs_score, 26.0)
        self.assertEqual(obs_start_end, [(4, 8), (1, 4)])

        # Fails when either input is passed as a TabularMSA
        self.assertRaises(TypeError, local_pairwise_align_protein,
                          TabularMSA([Protein("HEAGAWGHEE",
                                      metadata={'id': "s1"})]),
                          Protein("PAWHEAE", metadata={'id': "s2"}),
                          gap_open_penalty=10.,
                          gap_extend_penalty=5.)
        self.assertRaises(TypeError, local_pairwise_align_protein,
                          Protein("HEAGAWGHEE", metadata={'id': "s1"}),
                          TabularMSA([Protein("PAWHEAE",
                                      metadata={'id': "s2"})]),
                          gap_open_penalty=10., gap_extend_penalty=5.)

        # TypeError on invalid input
        self.assertRaises(TypeError, local_pairwise_align_protein,
                          42, Protein("HEAGAWGHEE"))
        self.assertRaises(TypeError, local_pairwise_align_protein,
                          Protein("HEAGAWGHEE"), 42)

    def test_global_pairwise_align_nucleotide(self):
        obs_msa, obs_score, obs_start_end = global_pairwise_align_nucleotide(
            DNA("GACCTTGACCAGGTACC"), DNA("GAACTTTGACGTAAC"),
            gap_open_penalty=5., gap_extend_penalty=0.5, match_score=5,
            mismatch_score=-4)

        self.assertEqual(obs_msa, TabularMSA([DNA("G-ACCTTGACCAGGTACC"),
                                              DNA("GAACTTTGAC---GTAAC")]))
        self.assertEqual(obs_score, 41.0)
        self.assertEqual(obs_start_end, [(0, 16), (0, 14)])

        obs_msa, obs_score, obs_start_end = global_pairwise_align_nucleotide(
            DNA("GACCTTGACCAGGTACC"), DNA("GAACTTTGACGTAAC"),
            gap_open_penalty=10., gap_extend_penalty=0.5, match_score=5,
            mismatch_score=-4)

        self.assertEqual(obs_msa, TabularMSA([DNA("-GACCTTGACCAGGTACC"),
                                              DNA("GAACTTTGAC---GTAAC")]))
        self.assertEqual(obs_score, 32.0)
        self.assertEqual(obs_start_end, [(0, 16), (0, 14)])

        # DNA sequences with metadata
        obs_msa, obs_score, obs_start_end = global_pairwise_align_nucleotide(
            DNA("GACCTTGACCAGGTACC", metadata={'id': "s1"}),
            DNA("GAACTTTGACGTAAC", metadata={'id': "s2"}),
            gap_open_penalty=10., gap_extend_penalty=0.5, match_score=5,
            mismatch_score=-4)

        self.assertEqual(obs_msa, TabularMSA([DNA("-GACCTTGACCAGGTACC"),
                                              DNA("GAACTTTGAC---GTAAC")]))
        self.assertEqual(obs_score, 32.0)
        self.assertEqual(obs_start_end, [(0, 16), (0, 14)])

        # Align one DNA sequence and one TabularMSA, score computed manually
        obs_msa, obs_score, obs_start_end = global_pairwise_align_nucleotide(
            TabularMSA([DNA("GACCTTGACCAGGTACC", metadata={'id': "s1"}),
                        DNA("GACCATGACCAGGTACC", metadata={'id': "s2"})]),
            DNA("GAACTTTGACGTAAC", metadata={'id': "s3"}),
            gap_open_penalty=10., gap_extend_penalty=0.5, match_score=5,
            mismatch_score=-4)

        self.assertEqual(obs_msa, TabularMSA([DNA("-GACCTTGACCAGGTACC"),
                                              DNA("-GACCATGACCAGGTACC"),
                                              DNA("GAACTTTGAC---GTAAC")]))
        self.assertEqual(obs_score, 27.5)
        self.assertEqual(obs_start_end, [(0, 16), (0, 14)])

        # TypeError on invalid input
        self.assertRaises(TypeError, global_pairwise_align_nucleotide,
                          42, DNA("ACGT"))
        self.assertRaises(TypeError, global_pairwise_align_nucleotide,
                          DNA("ACGT"), 42)

    def test_global_pairwise_align_nucleotide_invalid_dtype(self):
        with six.assertRaisesRegex(self, TypeError,
                                   "TabularMSA with DNA or RNA dtype.*dtype "
                                   "'Protein'"):
            global_pairwise_align_nucleotide(TabularMSA([DNA('ACGT')]),
                                             TabularMSA([Protein('PAW')]))

    def test_local_pairwise_align_nucleotide(self):
        obs_msa, obs_score, obs_start_end = local_pairwise_align_nucleotide(
            DNA("GACCTTGACCAGGTACC"), DNA("GAACTTTGACGTAAC"),
            gap_open_penalty=5., gap_extend_penalty=0.5, match_score=5,
            mismatch_score=-4)

        self.assertEqual(obs_msa, TabularMSA([DNA("ACCTTGACCAGGTACC"),
                                              DNA("ACTTTGAC---GTAAC")]))
        self.assertEqual(obs_score, 41.0)
        self.assertEqual(obs_start_end, [(1, 16), (2, 14)])

        obs_msa, obs_score, obs_start_end = local_pairwise_align_nucleotide(
            DNA("GACCTTGACCAGGTACC"), DNA("GAACTTTGACGTAAC"),
            gap_open_penalty=10., gap_extend_penalty=5., match_score=5,
            mismatch_score=-4)

        self.assertEqual(obs_msa, TabularMSA([DNA("ACCTTGAC"),
                                              DNA("ACTTTGAC")]))
        self.assertEqual(obs_score, 31.0)
        self.assertEqual(obs_start_end, [(1, 8), (2, 9)])

        # DNA sequences with metadata
        obs_msa, obs_score, obs_start_end = local_pairwise_align_nucleotide(
            DNA("GACCTTGACCAGGTACC", metadata={'id': "s1"}),
            DNA("GAACTTTGACGTAAC", metadata={'id': "s2"}),
            gap_open_penalty=10., gap_extend_penalty=5., match_score=5,
            mismatch_score=-4)

        self.assertEqual(obs_msa, TabularMSA([DNA("ACCTTGAC"),
                                              DNA("ACTTTGAC")]))
        self.assertEqual(obs_score, 31.0)
        self.assertEqual(obs_start_end, [(1, 8), (2, 9)])

        # Fails when either input is passed as a TabularMSA
        self.assertRaises(TypeError, local_pairwise_align_nucleotide,
                          TabularMSA([DNA("GACCTTGACCAGGTACC",
                                          metadata={'id': "s1"})]),
                          DNA("GAACTTTGACGTAAC", metadata={'id': "s2"}),
                          gap_open_penalty=10., gap_extend_penalty=5.,
                          match_score=5, mismatch_score=-4)
        self.assertRaises(TypeError, local_pairwise_align_nucleotide,
                          DNA("GACCTTGACCAGGTACC", metadata={'id': "s1"}),
                          TabularMSA([DNA("GAACTTTGACGTAAC",
                                      metadata={'id': "s2"})]),
                          gap_open_penalty=10., gap_extend_penalty=5.,
                          match_score=5, mismatch_score=-4)

        # TypeError on invalid input
        self.assertRaises(TypeError, local_pairwise_align_nucleotide,
                          42, DNA("ACGT"))
        self.assertRaises(TypeError, local_pairwise_align_nucleotide,
                          DNA("ACGT"), 42)

    def test_nucleotide_aligners_use_substitution_matrices(self):
        alt_sub = make_identity_substitution_matrix(10, -10)
        # alternate substitution matrix yields different alignment (the
        # aligned sequences and the scores are different) with local alignment
        msa_no_sub, score_no_sub, start_end_no_sub = \
            local_pairwise_align_nucleotide(
                DNA("GACCTTGACCAGGTACC"), DNA("GAACTTTGACGTAAC"),
                gap_open_penalty=10., gap_extend_penalty=5., match_score=5,
                mismatch_score=-4)

        msa_alt_sub, score_alt_sub, start_end_alt_sub = \
            local_pairwise_align_nucleotide(
                DNA("GACCTTGACCAGGTACC"), DNA("GAACTTTGACGTAAC"),
                gap_open_penalty=10., gap_extend_penalty=5., match_score=5,
                mismatch_score=-4, substitution_matrix=alt_sub)

        self.assertNotEqual(msa_no_sub, msa_alt_sub)
        self.assertNotEqual(score_no_sub, score_alt_sub)
        self.assertNotEqual(start_end_no_sub, start_end_alt_sub)

        # alternate substitution matrix yields different alignment (the
        # aligned sequences and the scores are different) with global alignment
        msa_no_sub, score_no_sub, start_end_no_sub = \
            global_pairwise_align_nucleotide(
                DNA("GACCTTGACCAGGTACC"), DNA("GAACTTTGACGTAAC"),
                gap_open_penalty=10., gap_extend_penalty=5., match_score=5,
                mismatch_score=-4)

        msa_alt_sub, score_alt_sub, start_end_alt_sub = \
            global_pairwise_align_nucleotide(
                DNA("GACCTTGACCAGGTACC"), DNA("GAACTTTGACGTAAC"),
                gap_open_penalty=10., gap_extend_penalty=5., match_score=5,
                mismatch_score=-4, substitution_matrix=alt_sub)

        self.assertNotEqual(msa_no_sub, msa_alt_sub)
        self.assertNotEqual(score_no_sub, score_alt_sub)
        self.assertEqual(start_end_no_sub, start_end_alt_sub)

    def test_local_pairwise_align_invalid_type(self):
        with six.assertRaisesRegex(self, TypeError,
                                   'GrammaredSequence.*Sequence'):
            local_pairwise_align(DNA('ACGT'), Sequence('ACGT'), 1.0, 1.0, {})

    def test_local_pairwise_align_type_mismatch(self):
        with six.assertRaisesRegex(self, TypeError,
                                   "same type: 'DNA' != 'RNA'"):
            local_pairwise_align(DNA('ACGT'), RNA('ACGU'), 1.0, 1.0, {})

    def test_init_matrices_sw(self):
        expected_score_m = np.zeros((5, 4))
        expected_tback_m = [[0, 0, 0, 0],
                            [0, -1, -1, -1],
                            [0, -1, -1, -1],
                            [0, -1, -1, -1],
                            [0, -1, -1, -1]]
        actual_score_m, actual_tback_m = _init_matrices_sw(
            TabularMSA([DNA('AAA', metadata={'id': 'id'})]),
            TabularMSA([DNA('AAAA', metadata={'id': 'id'})]), 5, 2)
        np.testing.assert_array_equal(actual_score_m, expected_score_m)
        np.testing.assert_array_equal(actual_tback_m, expected_tback_m)

    def test_init_matrices_nw(self):
        expected_score_m = [[0, -5, -7, -9],
                            [-5, 0, 0, 0],
                            [-7, 0, 0, 0],
                            [-9, 0, 0, 0],
                            [-11, 0, 0, 0]]
        expected_tback_m = [[0, 3, 3, 3],
                            [2, -1, -1, -1],
                            [2, -1, -1, -1],
                            [2, -1, -1, -1],
                            [2, -1, -1, -1]]
        actual_score_m, actual_tback_m = _init_matrices_nw(
            TabularMSA([DNA('AAA', metadata={'id': 'id'})]),
            TabularMSA([DNA('AAAA', metadata={'id': 'id'})]), 5, 2)
        np.testing.assert_array_equal(actual_score_m, expected_score_m)
        np.testing.assert_array_equal(actual_tback_m, expected_tback_m)

    def test_compute_substitution_score(self):
        # these results were computed manually
        subs_m = make_identity_substitution_matrix(5, -4)
        gap_chars = set('-.')

        self.assertEqual(
            _compute_substitution_score(['A'], ['A'], subs_m, 0, gap_chars),
            5.0)
        self.assertEqual(
            _compute_substitution_score(['A', 'A'], ['A'], subs_m, 0,
                                        gap_chars),
            5.0)
        self.assertEqual(
            _compute_substitution_score(['A', 'C'], ['A'], subs_m, 0,
                                        gap_chars),
            0.5)
        self.assertEqual(
            _compute_substitution_score(['A', 'C'], ['A', 'C'], subs_m, 0,
                                        gap_chars),
            0.5)
        self.assertEqual(
            _compute_substitution_score(['A', 'A'], ['A', '-'], subs_m, 0,
                                        gap_chars),
            2.5)
        self.assertEqual(
            _compute_substitution_score(['A', 'A'], ['A', '-'], subs_m, 1,
                                        gap_chars),
            3)

        # alt subs_m
        subs_m = make_identity_substitution_matrix(1, -2)

        self.assertEqual(
            _compute_substitution_score(['A', 'A'], ['A', '-'], subs_m, 0,
                                        gap_chars),
            0.5)

    def test_compute_score_and_traceback_matrices(self):
        # these results were computed manually
        expected_score_m = [[0, -5, -7, -9],
                            [-5, 2, -3, -5],
                            [-7, -3, 4, -1],
                            [-9, -5, -1, 6],
                            [-11, -7, -3, 1]]
        expected_tback_m = [[0, 3, 3, 3],
                            [2, 1, 3, 3],
                            [2, 2, 1, 3],
                            [2, 2, 2, 1],
                            [2, 2, 2, 2]]
        m = make_identity_substitution_matrix(2, -1)
        actual_score_m, actual_tback_m = _compute_score_and_traceback_matrices(
            TabularMSA([DNA('ACG', metadata={'id': 'id'})]),
            TabularMSA([DNA('ACGT', metadata={'id': 'id'})]), 5, 2, m)
        np.testing.assert_array_equal(actual_score_m, expected_score_m)
        np.testing.assert_array_equal(actual_tback_m, expected_tback_m)

        # different sequences
        # these results were computed manually
        expected_score_m = [[0, -5, -7, -9],
                            [-5, 2, -3, -5],
                            [-7, -3, 4, -1],
                            [-9, -5, -1, 3],
                            [-11, -7, -3, -2]]
        expected_tback_m = [[0, 3, 3, 3],
                            [2, 1, 3, 3],
                            [2, 2, 1, 3],
                            [2, 2, 2, 1],
                            [2, 2, 2, 1]]
        m = make_identity_substitution_matrix(2, -1)
        actual_score_m, actual_tback_m = _compute_score_and_traceback_matrices(
            TabularMSA([DNA('ACC', metadata={'id': 'id'})]),
            TabularMSA([DNA('ACGT', metadata={'id': 'id'})]), 5, 2, m)
        np.testing.assert_array_equal(actual_score_m, expected_score_m)
        np.testing.assert_array_equal(actual_tback_m, expected_tback_m)

        # four sequences provided in two alignments
        # these results were computed manually
        expected_score_m = [[0, -5, -7, -9],
                            [-5, 2, -3, -5],
                            [-7, -3, 4, -1],
                            [-9, -5, -1, 3],
                            [-11, -7, -3, -2]]
        expected_tback_m = [[0, 3, 3, 3],
                            [2, 1, 3, 3],
                            [2, 2, 1, 3],
                            [2, 2, 2, 1],
                            [2, 2, 2, 1]]
        m = make_identity_substitution_matrix(2, -1)
        actual_score_m, actual_tback_m = _compute_score_and_traceback_matrices(
            TabularMSA([DNA('ACC', metadata={'id': 's1'}),
                        DNA('ACC', metadata={'id': 's2'})]),
            TabularMSA([DNA('ACGT', metadata={'id': 's3'}),
                        DNA('ACGT', metadata={'id': 's4'})]), 5, 2, m)
        np.testing.assert_array_equal(actual_score_m, expected_score_m)
        np.testing.assert_array_equal(actual_tback_m, expected_tback_m)

    def test_compute_score_and_traceback_matrices_invalid(self):
        # if the sequence contains a character that is not in the
        # substitution matrix, an informative error should be raised
        m = make_identity_substitution_matrix(2, -1)
        self.assertRaises(ValueError, _compute_score_and_traceback_matrices,
                          TabularMSA([DNA('AWG', metadata={'id': 'id'})]),
                          TabularMSA([DNA('ACGT', metadata={'id': 'id'})]),
                          5, 2, m)

    def test_traceback(self):
        score_m = [[0, -5, -7, -9],
                   [-5, 2, -3, -5],
                   [-7, -3, 4, -1],
                   [-9, -5, -1, 6],
                   [-11, -7, -3, 1]]
        score_m = np.array(score_m)
        tback_m = [[0, 3, 3, 3],
                   [2, 1, 3, 3],
                   [2, 2, 1, 3],
                   [2, 2, 2, 1],
                   [2, 2, 2, 2]]
        tback_m = np.array(tback_m)
        # start at bottom-right
        expected = ([DNA("ACG-")], [DNA("ACGT")], 1, 0, 0)
        actual = _traceback(tback_m, score_m,
                            TabularMSA([DNA('ACG', metadata={'id': ''})]),
                            TabularMSA([DNA('ACGT', metadata={'id': ''})]),
                            4, 3)
        self.assertEqual(actual, expected)

        # four sequences in two alignments
        score_m = [[0, -5, -7, -9],
                   [-5, 2, -3, -5],
                   [-7, -3, 4, -1],
                   [-9, -5, -1, 6],
                   [-11, -7, -3, 1]]
        score_m = np.array(score_m)
        tback_m = [[0, 3, 3, 3],
                   [2, 1, 3, 3],
                   [2, 2, 1, 3],
                   [2, 2, 2, 1],
                   [2, 2, 2, 2]]
        tback_m = np.array(tback_m)
        # start at bottom-right
        expected = ([DNA("ACG-"),
                     DNA("ACG-")],
                    [DNA("ACGT"),
                     DNA("ACGT")],
                    1, 0, 0)
        actual = _traceback(tback_m, score_m,
                            TabularMSA([DNA('ACG', metadata={'id': 's1'}),
                                        DNA('ACG', metadata={'id': 's2'})]),
                            TabularMSA([DNA('ACGT', metadata={'id': 's3'}),
                                        DNA('ACGT', metadata={'id': 's4'})]),
                            4, 3)
        self.assertEqual(actual, expected)

        # start at highest-score
        expected = ([DNA("ACG")],
                    [DNA("ACG")], 6, 0, 0)
        actual = _traceback(tback_m, score_m,
                            TabularMSA([DNA('ACG', metadata={'id': ''})]),
                            TabularMSA([DNA('ACGT', metadata={'id': ''})]),
                            3, 3)
        self.assertEqual(actual, expected)

        # terminate traceback before top-right
        tback_m = [[0, 3, 3, 3],
                   [2, 1, 3, 3],
                   [2, 2, 0, 3],
                   [2, 2, 2, 1],
                   [2, 2, 2, 2]]
        tback_m = np.array(tback_m)
        expected = ([DNA("G")],
                    [DNA("G")], 6, 2, 2)
        actual = _traceback(tback_m, score_m,
                            TabularMSA([DNA('ACG', metadata={'id': ''})]),
                            TabularMSA([DNA('ACGT', metadata={'id': ''})]),
                            3, 3)
        self.assertEqual(actual, expected)

    def test_first_largest(self):
        l = [(5, 'a'), (5, 'b'), (5, 'c')]
        self.assertEqual(_first_largest(l), (5, 'a'))
        l = [(5, 'c'), (5, 'b'), (5, 'a')]
        self.assertEqual(_first_largest(l), (5, 'c'))
        l = [(5, 'c'), (6, 'b'), (5, 'a')]
        self.assertEqual(_first_largest(l), (6, 'b'))
        # works for more than three entries
        l = [(5, 'c'), (6, 'b'), (5, 'a'), (7, 'd')]
        self.assertEqual(_first_largest(l), (7, 'd'))
        # Note that max([(5, 'a'), (5, 'c')]) == max([(5, 'c'), (5, 'a')])
        # but for the purposes needed here, we want the max to be the same
        # regardless of what the second item in the tuple is.

if __name__ == "__main__":
    main()
