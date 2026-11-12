from types import SimpleNamespace

from chemctl.basis_metadata import BasisEvidence
from chemctl.parsing import parse_output


def test_sdd_light_atom_basis_and_ecp(tmp_path, monkeypatch):
    # Synthetic format evidence, not a real electronic structure calculation.
    path = tmp_path / 'mixed.log'
    path.write_text('''Entering Gaussian System
 #p B3LYP/genecp
 -------------------
 General basis read from cards: (5D, 7F)
 Centers: 1
 SDD
 ****
 Centers: 2 3
 4
 6-31G*
 ****
 SCF Done: E(RB3LYP) = -100.0 A.U.
 Normal termination of Gaussian
''')
    data = SimpleNamespace(metadata={'methods': ['DFT'], 'functional': 'B3LYP', 'basis_set': 'GenECP'},
                           atomnos=[78, 6, 1, 8], coreelectrons=[60, 0, 0, 0])
    monkeypatch.setattr('chemctl.parsing.cclib.io.ccopen', lambda *a, **kw: SimpleNamespace(parse=lambda: data))
    result = parse_output(path)
    assert result['basis_set'] == 'Pt: SDD; C/H/O: 6-31G(d)'
    assert result['basis_groups'][1]['centers'] == [2, 3, 4]
    assert result['mixed_basis'] is True
    assert result['ecp_centers'][0]['core_electrons'] == 60


def test_latest_basis_and_no_ecp_inference():
    evidence = BasisEvidence()
    for n, line in enumerate(['General basis read from cards:', 'Centers: 1', 'SDD', '****']):
        evidence.feed(line, n)
    assert evidence.result(['Pt'], [], 'x')['ecp_centers'] == []
    evidence.feed('Standard basis: def2-SVP', 5)
    assert evidence.result(['Pt'], [], 'x')['basis_groups'] == []
