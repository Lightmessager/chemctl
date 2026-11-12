"""Streaming evidence extraction plus cclib scientific metadata.

We deliberately do not infer TS validity or align geometry and energy by array index.
"""
import hashlib
import logging
import math
import re
from pathlib import Path

import cclib
from cclib.parser.utils import PeriodicTable
from .chemistry_metadata import resolve_metadata
from .basis_metadata import BasisEvidence

PARSER_VERSION = "0.1.4+cclib-" + cclib.__version__
NUMBER = r"[-+]?\d+(?:\.\d*)?(?:[DEde][-+]?\d+)?"
ORCA_ENERGY = re.compile(r"FINAL SINGLE POINT ENERGY\s+(" + NUMBER + ")")
GAUSSIAN_ENERGY = re.compile(r"SCF Done:\s+E\(([^)]+)\)\s*=\s*(" + NUMBER + ")")


def number(value):
    value = float(value.replace("D", "E").replace("d", "e"))
    return value if math.isfinite(value) else None


def fingerprint(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_output(path: Path):
    before = path.stat()
    result = {"engine": None, "engine_version": None, "parser_version": PARSER_VERSION,
              "method": None, "basis_set": None, "charge": None, "multiplicity": None,
              "atom_count": None, "atom_symbols": [], "final_energy_eh": None,
              "status": "unsupported", "termination": None,
              "calculation_status": None, "frequency_summary": None,
              "energies": [], "structures": [], "frequencies": [], "thermochemistry": {},
              "convergence": {"geometry": None}, "warnings": [], "field_status": {},
              "source_path": str(path), "stages": []}
    normal, error, last_activity = 0, 0, 0
    stage_index = 0
    coordinate_block = None
    metadata = {}
    basis_evidence, core_electrons = BasisEvidence(), []
    keywords, route_lines = '', None
    with path.open(encoding="utf-8", errors="replace") as source:
        for line_no, line in enumerate(source, 1):
            basis_evidence.feed(line, line_no)
            if line.lstrip().startswith('#'):
                route_lines = [re.sub(r'^\s*#(?:[pnt](?=\s))?\s*', '', line, flags=re.I).strip()]
            elif route_lines is not None:
                if re.match(r'^\s*-{5,}', line) or not line.strip():
                    keywords = ' '.join(route_lines)
                    route_lines = None
                else:
                    route_lines.append(line.strip())
            if line.strip() == 'INPUT FILE':
                keywords = ''
            orca_input = re.match(r'\s*\|\s*\d+>\s*!(.*)', line)
            if orca_input:
                keywords += ' ' + orca_input[1].strip()
            if "O   R   C   A" in line or "Entering Gaussian System" in line:
                last_activity = line_no
                if normal:
                    stage_index += 1
            if "CARTESIAN COORDINATES (ANGSTROEM)" in line:
                coordinate_block = {"index": len(result["structures"]), "unit": "angstrom", "symbols": [],
                    "coordinates": [], "stage_id": None, "source_location": {"path": str(path), "line": line_no}}
                last_activity = line_no
                continue
            if coordinate_block is not None:
                xyz = re.match(r"\s*([A-Z][a-z]?)\s+(" + NUMBER + r")\s+(" + NUMBER + r")\s+(" + NUMBER + r")\s*$", line)
                if xyz:
                    coordinate_block["symbols"].append(xyz[1])
                    coordinate_block["coordinates"].append([number(xyz[i]) for i in (2, 3, 4)])
                    continue
                if not line.strip() and coordinate_block["symbols"]:
                    result["structures"].append(coordinate_block)
                    result["atom_symbols"] = coordinate_block["symbols"]
                    result["atom_count"] = len(coordinate_block["symbols"])
                    coordinate_block = None
                elif line.strip() and set(line.strip()) != {"-"}:
                    coordinate_block = None
            version = re.search(r"Program Version\s+(\S+)", line)
            if version:
                result["engine_version"] = version[1]
            for field, pattern in (("charge", r"Total Charge\s+Charge\s+\.+\s+(-?\d+)"),
                                   ("multiplicity", r"Multiplicity\s+Mult\s+\.+\s+(\d+)")):
                match = re.search(pattern, line)
                if match:
                    result[field] = int(match[1])
            if "O   R   C   A" in line or "ORCA" in line:
                result["engine"] = "orca"
            if "Gaussian" in line or "SCF Done:" in line:
                result["engine"] = "gaussian09d"
            if "Entering Link 1" in line or "$new_job" in line.lower():
                stage_index += 1
                last_activity = line_no
            hit = ORCA_ENERGY.search(line)
            gaussian = GAUSSIAN_ENERGY.search(line)
            if hit or gaussian:
                result["engine"] = "orca" if hit else "gaussian09d"
                value = number(hit[1] if hit else gaussian[2])
                result["energies"].append({"value": value, "unit": "Eh", "kind": "electronic" if hit else "scf",
                    "step": len(result["energies"]), "stage_id": f"stage_{stage_index}",
                    "source_location": {"path": str(path), "line": line_no}})
                last_activity = line_no
                if gaussian:
                    result["method"] = gaussian[1]
            if "ORCA TERMINATED NORMALLY" in line or "Normal termination of Gaussian" in line:
                normal = line_no
                result["termination"] = line.strip()
            if "Error termination" in line or "ORCA finished by error termination" in line:
                error = line_no
                result["termination"] = line.strip()
            if "THE OPTIMIZATION HAS CONVERGED" in line or "Optimization completed." in line:
                result["convergence"]["geometry"] = True
            if "optimization has not converged" in line.lower() or "Optimization stopped." in line:
                result["convergence"]["geometry"] = False
            freq = re.search(r"Frequencies --\s+(.+)", line)
            ofreq = re.match(r"\s*\d+:\s+(" + NUMBER + r")\s+cm\*\*-1", line)
            if freq or ofreq:
                for raw in (freq[1].split() if freq else [ofreq[1]]):
                    result["frequencies"].append({"value": number(raw), "unit": "cm^-1", "mode": len(result["frequencies"]),
                        "stage_id": f"stage_{stage_index}", "source_location": {"path": str(path), "line": line_no}})
                last_activity = line_no
    if not result["engine"]:
        result["warnings"].append("Unrecognized output; only ORCA and Gaussian are supported.")
        return result
    complete = normal > max(error, last_activity)
    result["status"] = "parsed" if complete else "partial"
    result["calculation_status"] = "completed" if complete else "failed" if error > normal else "incomplete"
    # A cclib failure leaves the independently extracted evidence available.
    try:
        parser = cclib.io.ccopen(str(path), loglevel=logging.ERROR)
        data = parser.parse() if parser else None
        if data is not None:
            metadata = data.metadata
            core_electrons = getattr(data, 'coreelectrons', [])
            extra = dict(engine_version=metadata.get("package_version"), basis_set=metadata.get("basis_set"),
                         charge=getattr(data, "charge", None), multiplicity=getattr(data, "mult", None),
                         atom_count=getattr(data, "natom", None))
            result.update({key: value for key, value in extra.items() if value is not None})
            if hasattr(data, "atomnos"):
                table = PeriodicTable()
                result["atom_symbols"] = [table.element[int(n)] for n in data.atomnos]
            if hasattr(data, "atomcoords") and not result["structures"]:
                for index, coords in enumerate(data.atomcoords):
                    result["structures"].append({"index": index, "unit": "angstrom",
                        "symbols": result["atom_symbols"], "coordinates": coords.tolist(),
                        "stage_id": None, "source_location": {"path": str(path), "parser_attribute": f"atomcoords[{index}]"}})
            for name in ("zpve", "enthalpy", "freeenergy", "entropy", "temperature"):
                if hasattr(data, name):
                    value = float(getattr(data, name))
                    result["thermochemistry"][name] = {"value": value if math.isfinite(value) else None,
                        "unit": "K" if name == "temperature" else "Eh/K" if name == "entropy" else "Eh",
                        "source_location": {"path": str(path), "parser_attribute": name}}
        else:
            result["warnings"].append("cclib could not identify this output; only streaming markers were extracted.")
            result["status"] = "partial"
    except Exception as exc:
        # Third-party parser boundary: one damaged output must not kill a batch.
        result["warnings"].append(f"cclib could not finish: {type(exc).__name__}: {exc}")
        result["status"] = "partial"
    result.update(resolve_metadata(metadata, result['method'], keywords))
    result.update(basis_evidence.result(result['atom_symbols'], core_electrons, str(path)))
    if result['basis_summary']:
        result['basis_set'] = result['basis_summary']
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        complete = False
        result["status"] = "partial"
        result["calculation_status"] = "incomplete"
        result["warnings"].append("Source changed during parsing; parse again after the writer stops.")
    if complete and result["energies"]:
        result["final_energy_eh"] = result["energies"][-1]["value"]
    else:
        result["warnings"].append("No complete final calculation; energy entries are observations, not a final result.")
    for index in sorted({e["stage_id"] for e in result["energies"]}):
        result["stages"].append({"stage_id": index, "stage_type": "unknown", "warning": "Stage classification is not yet supported."})
    values = [f["value"] for f in result["frequencies"] if f["value"] is not None]
    result["frequency_summary"] = {"count": len(values), "imaginary_count": sum(v < 0 for v in values)} if values else None
    for field in ("method", "basis_set", "solvent_name", "solvent_model", "charge", "multiplicity", "atom_count", "final_energy_eh"):
        result["field_status"][field] = "available" if result[field] is not None else "not_available_in_supported_parse"
    return result
