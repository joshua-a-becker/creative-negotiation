"""Refresh the feedback materials using the current expanded configuration.

Standard-library only; no model calls, keys, hard-coded computer paths or installs.
The HTML owns the survey wording/layout. This script refreshes its role blocks
and exports its questions in the existing Empirica scales/questions YAML format.
Use --template once to import an existing survey HTML; otherwise update in place.
"""
from pathlib import Path
from html.parser import HTMLParser
import argparse
import ast
import hashlib
import json
import re
from role_presentation import role_narrative, narrative_to_html

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'experiment materials'
HTML_NAME = 'Mockup - Creative Negotiations Feedback Survey.html'
CONFIG = ROOT / 'app/config/large-215.json'


class Element:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.walk()

    def text(self):
        if self.tag == 'br':
            return '\n'
        return ''.join(c.text() if isinstance(c, Element) else c for c in self.children)


class Document(HTMLParser):
    VOID = {'input', 'meta', 'link', 'br', 'hr', 'img', 'source', 'wbr'}

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = Element()
        self.stack = [self.root]
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = Element(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, value):
        self.stack[-1].children.append(value)

    def by_id(self, ident):
        return next(n for n in self.root.walk() if n.attrs.get('id') == ident)


def clean(node):
    return re.sub(r'\s+', ' ', node.text()).strip()


def has_class(node, name):
    return name in node.attrs.get('class', '').split()


def question_label(node):
    return re.sub(r'^Q\d+\.\s*', '', clean(node))


def js_array(source, name):
    match = re.search(r'\bconst ' + re.escape(name) + r'\s*=\s*(\[.*?\]);', source, re.S)
    if not match:
        raise ValueError('Missing survey array: ' + name)
    value = ast.literal_eval(match.group(1))
    assert isinstance(value, list) and all(isinstance(x, str) for x in value)
    return value


def role_markdown(blocks, *, preserve_italics=False):
    """Export the bold-only Markdown supported by the current Empirica reader.

    Its displayed output recognizes **bold**, but leaves *italic* delimiters
    visible (including the extra star from ***bold italic***). Do not emit
    those unsupported markers or replace them with unverified HTML. Original
    italic flags stay in the source blocks and the full-format HTML mockup.
    Full Markdown remains available explicitly for other compatible readers.
    """
    paragraphs = []
    for block in blocks:
        groups = []
        for run in block['runs']:
            flags = (bool(run.get('bold')),
                     bool(run.get('italic')) and preserve_italics,
                     bool(run.get('underline')))
            if groups and groups[-1][0] == flags:
                groups[-1][1] += run.get('text', '')
            else:
                groups.append([flags, run.get('text', '')])
        parts = []
        for (bold, italic, underline), text in groups:
            if not text.strip():
                parts.append(text)
                continue
            leading = text[:len(text) - len(text.lstrip())]
            trailing = text[len(text.rstrip()):]
            value = text.strip()
            if underline:
                value = '<u>' + value + '</u>'
            marker = ('**' if bold else '') + ('*' if italic else '')
            parts.append(leading + marker + value + marker + trailing)
        paragraphs.append(''.join(parts))
    return '\n\n'.join(paragraphs)


def surveys_from_html(source):
    document = Document(source)
    labels = {}
    for node in document.root.walk():
        if node.tag == 'legend' or has_class(node, 'q-label'):
            match = re.match(r'^Q(\d+)\.', clean(node))
            if match:
                labels.setdefault(int(match.group(1)), question_label(node))
    statements, agree = js_array(source, 'statements'), js_array(source, 'scale')
    assert len(statements) == 5 and len(agree) == 5

    def choices(name):
        return [clean(n.parent) for n in document.root.walk()
                if n.tag == 'input' and n.attrs.get('name') == name]

    outputs = {}
    for role in ('Candidate', 'Recruiter'):
        prefix = role.lower()
        other_role = 'Recruiter' if role == 'Candidate' else 'Candidate'
        questions = [dict(id=f'q{i}', n=i, type='likert', scale='agree_5', label=t.replace('{other_role}', other_role))
                     for i, t in enumerate(statements, 1)]

        def add(n, kind, **fields):
            questions.append(dict(id=f'q{n}', n=n, type=kind, label=labels[n], **fields))

        add(6, 'open_text', hint='List the three required terms in your own words, one per line.')
        add(7, 'open_text', hint='Write the complete offer in ordinary language, as if you were sending it to the other party.')
        add(8, 'single_select', style='pills', options=choices('multipleClear'))
        add(9, 'open_text', hint='Write a complete counteroffer in ordinary language.')
        # Keep all essential content in the label for readers that omit hints.
        # Blank lines separate context, the actual offer, and the response task.
        questions[-1]['label'] = (labels[9].replace('the Recruiter', 'the ' + other_role)
                                 + '\n\n' + clean(document.by_id(prefix + 'Counter'))
                                 + '\n\n' + clean(document.by_id('counterResponsePrompt')))
        add(10, 'open_text', hint='Briefly walk us through your reasoning.')
        add(11, 'open_text', hint=document.by_id('featureFormatHint').text().strip(),
            placeholder=document.by_id('otherFeatures').attrs['placeholder'])
        priorities = document.by_id(prefix + 'Priorities')
        add(12, 'multi_select', hint='Select all that you think apply.',
            options=[clean(n) for n in priorities.walk() if n.tag == 'label' and has_class(n, 'option')])
        questions[-1]['label'] = question_label(next(n for n in priorities.walk() if n.tag == 'legend'))
        add(13, 'open_text', hint='Optional. Tell us what was unclear, unrealistic or worth improving.')
        add(14, 'likert', scale='experience_5')
        add(15, 'single_select', style='pills', options=choices('futurePanel'),
            hint='If you select Yes, we may add you to a panel contacted when the study or another pre-test goes live. This choice does not affect your payment.')
        outputs[role] = dict(scales={'agree_5': agree, 'experience_5': choices('experience')}, questions=questions)
    return outputs


def survey_yaml(data):
    """Emit only the mapping/list/scalar vocabulary used by the example survey."""
    scalar = lambda x: json.dumps(x, ensure_ascii=False)
    lines = ['scales:']
    for name, options in data['scales'].items():
        lines += ['  ' + name + ':'] + ['    - ' + scalar(x) for x in options]
    lines += ['', 'questions:']
    for question in data['questions']:
        lines.append('  - id: ' + question['id'])
        for key, value in question.items():
            if key == 'id':
                continue
            if isinstance(value, list):
                lines.append('    ' + key + ':')
                lines.extend('      - ' + scalar(x) for x in value)
            else:
                lines.append('    ' + key + ': ' + scalar(value))
        lines.append('')
    return '\n'.join(lines)


def build(template=None):
    scenario = json.loads(CONFIG.read_text(encoding='utf-8'))
    assert len(scenario['issues']) == 215 and len(scenario['required_issues']) == 3
    blocks = {role: scenario['roles'][role]['full_blocks'] for role in ('Candidate', 'Recruiter')}
    for role, value in blocks.items():
        plain = '\n\n'.join(''.join(r.get('text', '') for r in b['runs']) for b in value)
        assert plain == scenario['roles'][role]['full_text'], role + ': formatted/plain source mismatch'
    source = Path(template or OUT / HTML_NAME).read_text(encoding='utf-8')
    replacement = json.dumps(blocks, ensure_ascii=False).replace('<', '\\u003c')
    source, count = re.subn(r'(\bconst ROLE_BLOCKS\s*=\s*)\{.*?\};(?=\s*let assignedRole)',
                          lambda m: m.group(1) + replacement + ';', source, count=1, flags=re.S)
    assert count == 1, 'Expected the existing ROLE_BLOCKS slot in the survey.'
    source = source.replace('Notes for Joshua and the research team', 'Notes for the research team')
    version_note = '<!-- role-materials-source: app/config/large-215.json; sha256: ' + hashlib.sha256(CONFIG.read_bytes()).hexdigest() + ' -->'
    source = re.sub(r'\n<!-- role-materials-source:.*?-->', '', source)
    source = source.replace('</title>', '</title>\n' + version_note, 1)
    if 'id="materialVersion"' not in source:
        source = source.replace('<div class="preview-control"', '<p id="materialVersion">This preview uses the current expanded role materials. The full issue catalog is not shown to participants.</p>\n    <div class="preview-control"', 1)
    else:
        source = re.sub(
            r'(<p id="materialVersion">).*?(</p>)',
            r'\1This preview uses the current expanded role materials. The full issue catalog is not shown to participants.\2',
            source,
            count=1,
            flags=re.S,
        )

    # Share the same generated presentation with the local preview. Keep the
    # original ROLE_BLOCKS unchanged for provenance and future editing.
    presentation = json.dumps({role: narrative_to_html(role_narrative(value))
                               for role, value in blocks.items()}, ensure_ascii=False).replace('<', '\\u003c')
    source, count = re.subn(
        r'(?:  const ROLE_PRESENTATION = .*?;\n)?  function formattedRole\(role\)\{.*?\n  \}\n  function renderScenario',
        lambda m: '  const ROLE_PRESENTATION = ' + presentation + ';\n'
                  '  function formattedRole(role){\n    return ROLE_PRESENTATION[role];\n  }\n  function renderScenario',
        source, count=1, flags=re.S)
    assert count == 1, 'Expected the shared role-rendering function in the HTML.'
    surveys = surveys_from_html(source)
    intro = re.search(r'<div class="intro">(.*?)</div>', source, re.S).group(1).strip()
    # Same schema as the supplied narrative example. Do not disclose the hidden
    # 200-issue menu. This is the feedback/pretest material, not a scoring matrix.
    narrative = dict(roles=[dict(role_name=role, narrative=role_narrative(blocks[role]), RP=0, scoresheet={})
                            for role in ('Candidate', 'Recruiter')], tips=intro)
    OUT.mkdir(exist_ok=True)
    (OUT / HTML_NAME).write_text(source, encoding='utf-8', newline='\n')
    (OUT / 'role_materials_200.json').write_text(json.dumps(narrative, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # Keep the original combined export for existing links, but give each
    # assigned role a separate file using the same roles/tips loader schema.
    for role in narrative['roles']:
        single = dict(roles=[role], tips=narrative['tips'])
        (OUT / (role['role_name'].lower() + '_role_materials_200.json')).write_text(
            json.dumps(single, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for role, survey in surveys.items():
        (OUT / (role.lower() + '_feedback_survey.yaml')).write_text(survey_yaml(survey), encoding='utf-8')
    print('Updated the current expanded role materials, two role-specific surveys, and HTML preview. No API calls.')
    return narrative, surveys


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--template', type=Path, help='Existing survey HTML to import; normally omit.')
    build(parser.parse_args().template)
