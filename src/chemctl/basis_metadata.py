"""Gaussian named general-basis cards, indexed by the printed atom centers."""
import re

from .chemistry_metadata import basis_name


class BasisEvidence:
    def __init__(self):
        self.groups = []
        self.active = False
        self.centers = []
        self.names = []
        self.line = None
        self.reading_centers = False

    def feed(self, line, line_no):
        if 'General basis read from cards:' in line or 'Standard basis:' in line:
            self.groups = []
            self.centers, self.names = [], []
            self.active = 'General basis' in line
        if not self.active:
            return
        match = re.match(r'\s*Centers:\s*(.*)', line)
        if match:
            self.centers = [int(n) for n in match[1].split()]
            self.names, self.line = [], line_no
            self.reading_centers = True
        elif self.centers:
            value = line.strip()
            if self.reading_centers and re.fullmatch(r'\d+(?:\s+\d+)*', value):
                self.centers.extend(map(int, value.split()))
            elif value in ('****', '++++'):
                self.groups.append({'centers': self.centers, 'basis_set': ' + '.join(self.names) or 'custom (explicit shells)',
                                    'source_line': self.line})
                self.centers, self.names = [], []
            elif value:
                self.reading_centers = False
                if re.fullmatch(r'[A-Za-z0-9][\w+(),.*\'\-]*', value) and not value[0].isdigit():
                    self.names.append(basis_name(value))
                elif re.fullmatch(r'\d+-\d+\+*G[\w+(),.*\'\-]*', value, re.I):
                    self.names.append(basis_name(value))

    def result(self, symbols, core_electrons, path):
        groups = []
        for item in self.groups:
            centers = list(dict.fromkeys(item['centers']))
            elements = list(dict.fromkeys(symbols[n-1] for n in centers if 0 < n <= len(symbols)))
            groups.append({'centers': centers, 'elements': elements, 'basis_set': item['basis_set'],
                           'source_location': {'path': path, 'line': item['source_line']}})
        ecp = [{'center': n + 1, 'element': symbols[n] if n < len(symbols) else None,
                'core_electrons': int(count),
                'source_location': {'path': path, 'parser_attribute': f'coreelectrons[{n}]'}}
               for n, count in enumerate(core_electrons) if count > 0]
        summary = '; '.join(f"{'/'.join(g['elements']) or 'atoms ' + ','.join(map(str,g['centers']))}: {g['basis_set']}"
                            for g in groups)
        return {'basis_groups': groups, 'ecp_centers': ecp, 'basis_summary': summary or None,
                'mixed_basis': len({g['basis_set'] for g in groups}) > 1}
