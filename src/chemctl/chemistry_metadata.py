"""Display chemistry names without replacing specific evidence with method families."""
import re

ALIASES = {name.lower().replace('-', ''): name for name in (
    'M06', 'M06-2X', 'M06-L', 'M06-HF', 'M05', 'M05-2X', 'M08-HX', 'M08-SO',
    'M11', 'M11-L', 'MN15', 'MN15-L', 'B3LYP', 'BLYP', 'PBE', 'PBE0', 'PBE1PBE',
    'BP86', 'TPSS', 'TPSSh', 'CAM-B3LYP', 'wB97X', 'wB97X-D', 'wB97X-D3',
    'wB97X-D4', 'wB97M-V', 'wB97M-D3BJ', 'B97-3c', 'r2SCAN', 'r2SCAN-3c',
    'HF', 'MP2', 'MP3', 'MP4', 'CCSD', 'CCSD(T)', 'DLPNO-CCSD(T)',
    'RI-MP2', 'RI-SCS-MP2', 'B2PLYP', 'DSD-BLYP', 'PM3', 'PM6', 'AM1')}
ALIASES['pbe1pbe'] = 'PBE0'


def method_name(value):
    if not value:
        return None
    key = value.lower().replace('-', '')
    if key in ALIASES:
        return ALIASES[key]
    for prefix in ('ro', 'r', 'u'):
        if key.startswith(prefix) and key[len(prefix):] in ALIASES:
            return ALIASES[key[len(prefix):]]
    return value


def basis_name(value):
    if not value:
        return None
    # Only Pople star notation has this equivalence; preserve custom names.
    match = re.fullmatch(r'(\d+-\d+\+*G)(\*{1,2})', value, re.I)
    return match[1].upper() + ('(d,p)' if match[2] == '**' else '(d)') if match else value


def resolve_metadata(metadata, scf_method=None, keywords=''):
    methods = list(dict.fromkeys(metadata.get('methods', [])))
    reported = metadata.get('methods', [None])[-1] if metadata.get('methods') else None
    explicit = None
    requested_basis = None
    # Gaussian method/basis notation also preserves unfamiliar method names.
    pair = re.search(r'(?<![\w=(])([\w+\-]+(?:\([^()\s]*\))?)\s*/\s*([^\s]+)', keywords)
    if pair and not pair[1].isdigit() and pair[2].lower() not in ('j', 'c', 'jk'):
        explicit, requested_basis = pair[1], pair[2]
    tokens = keywords.replace('!', ' ').split()
    if not explicit:
        explicit = next((t for t in tokens if method_name(t) in ALIASES.values()), None)
    if not requested_basis:
        requested_basis = next((t for t in tokens if re.match(
            r'^(?:def2-|ma-def2-|(?:aug-|d-aug-)?cc-p|\d+-\d+\+*G|STO-\dG|LANL\d|SDD\b|Gen(?:ECP)?\b)', t, re.I)
            and not t.lower().endswith(('/j', '/c', '/jk'))), None)
    method = reported if reported and reported not in ('HF', 'DFT') else explicit or metadata.get('functional') or scf_method or reported
    solvent = metadata.get('solvent_name')
    model = metadata.get('solvent_model')
    match = re.search(r'\bsolvent\s*=\s*([\w-]+)', keywords, re.I)
    if not solvent and match:
        solvent = match[1].lower()
    match = re.search(r'\b(CPCM|SMD)\s*\(\s*([^()]+)\s*\)', keywords, re.I)
    if match:
        model, solvent = model or match[1].upper(), solvent or match[2].strip().lower()
    if not model and re.search(r'\bscrf\b', keywords, re.I):
        match = re.search(r'\b(SMD|IEFPCM|CPCM|PCM|COSMO|IPCM|SCIPCM)\b', keywords, re.I)
        model = match[1].upper() if match else None
    return dict(method=method_name(method), basis_set=basis_name(metadata.get('basis_set') or requested_basis),
                functional=method_name(metadata.get('functional')), method_families=methods,
                solvent_name=solvent, solvent_model=model, solvent_params=metadata.get('solvent_params', {}),
                method_raw=method, basis_set_requested=requested_basis, input_keywords=keywords or None)
