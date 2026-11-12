from chemctl.chemistry_metadata import resolve_metadata


def test_specific_functional_solvent_and_repeated_families():
    row = resolve_metadata({'methods': ['DFT', 'DFT'], 'functional': 'M062X',
                            'basis_set': '6-31G(d)', 'solvent_name': 'toluene',
                            'solvent_model': 'SMD-IEFPCM'}, 'RM062X')
    assert (row['method'], row['basis_set'], row['solvent_name'], row['solvent_model']) == (
        'M06-2X', '6-31G(d)', 'toluene', 'SMD-IEFPCM')
    assert row['method_families'] == ['DFT']


def test_method_basis_variants_and_auxiliary_basis():
    for route, method, basis in [
        ('opt M062x 6-31G* iop(1/8=6) scrf(smd,solvent=Toluene)', 'M06-2X', '6-31G(d)'),
        ('opt CAM-B3LYP/aug-cc-pVTZ', 'CAM-B3LYP', 'aug-cc-pVTZ'),
        ('UM062X/6-31+G**', 'M06-2X', '6-31+G(d,p)'),
        ('NewFunctional/GenECP', 'NewFunctional', 'GenECP'),
        ('! B3LYP def2-TZVP def2/J RIJCOSX CPCM(water)', 'B3LYP', 'def2-TZVP'),
    ]:
        row = resolve_metadata({}, keywords=route)
        assert (row['method'], row['basis_set']) == (method, basis)
    assert resolve_metadata({}, keywords='! PBE0 def2-SVP CPCM(water)')['solvent_name'] == 'water'
    assert resolve_metadata({'methods': ['HF', 'MP2', 'CCSD', 'CCSD(T)']})['method'] == 'CCSD(T)'
