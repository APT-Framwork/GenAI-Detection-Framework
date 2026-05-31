# -*- coding: utf-8 -*-
"""Fill the *editable* ESI Master poster Word canvas from the report content.
Produces PosterMaster_FR.docx and PosterMaster_EN.docx by populating the
official template '4. Annexe 2_Canevas PosterMaster.docx' in place — keeping
every text box / shape editable (no rasterisation)."""
import io, zipfile, shutil
from lxml import etree
from PIL import Image
from poster_content import FR, EN, REFS

SRC = '4. Annexe 2_Canevas PosterMaster.docx'
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
XMLNS = 'http://www.w3.org/XML/1998/namespace'
def q(t): return '{%s}%s' % (W, t)

# ---------------------------------------------------------------- figures
# image7.jpeg (1142x642, r=1.78) = Figure 1 frame ; image8.jpeg (863x299, r=2.89) = Figure 2 frame
def pad_jpeg(path, ratio, bg):
    im = Image.open(path).convert('RGB'); w, h = im.size
    if w / h < ratio:
        nw = int(round(h * ratio)); c = Image.new('RGB', (nw, h), bg); c.paste(im, ((nw - w) // 2, 0))
    else:
        nh = int(round(w / ratio)); c = Image.new('RGB', (w, nh), bg); c.paste(im, (0, (nh - h) // 2))
    b = io.BytesIO(); c.save(b, 'JPEG', quality=92); return b.getvalue()

FIG1 = pad_jpeg('figures/The 7 Steps -ckc.png', 1142 / 642, (0, 0, 0))
FIG2 = pad_jpeg('figures/ml_domain.png',        863 / 299, (255, 255, 255))

# ---------------------------------------------------------------- helpers
def truns(p):
    """direct text-bearing runs of a paragraph (ignores nested drawing text)."""
    return [r for r in p.findall(q('r')) if r.find(q('t')) is not None]

def ptext(p):
    return ''.join((r.find(q('t')).text or '') for r in truns(p))

def set_sz(p, half_pt):
    """force the font size (in half-points) of a paragraph's first text run."""
    rs = truns(p)
    if not rs:
        return
    rpr = rs[0].find(q('rPr'))
    if rpr is None:
        return
    for tag in ('sz', 'szCs'):
        e = rpr.find(q(tag))
        if e is None:
            e = etree.SubElement(rpr, q(tag))
        e.set(q('val'), str(half_pt))

def strip_numpr(p):
    """drop list auto-numbering from a paragraph (so our own bullet prefix is uniform)."""
    pPr = p.find(q('pPr'))
    if pPr is not None:
        np = pPr.find(q('numPr'))
        if np is not None:
            pPr.remove(np)

def set_para(p, text):
    """write *text* into the paragraph's first run, blank the rest (keeps formatting)."""
    rs = truns(p)
    if not rs:
        return False
    t0 = rs[0].find(q('t')); t0.text = text; t0.set('{%s}space' % XMLNS, 'preserve')
    for r in rs[1:]:
        r.find(q('t')).text = ''
    return True

def is_dots(s):
    s = s.strip()
    return bool(s) and set(s) <= set('….. ')

def boxes(root):
    return root.findall('.//' + q('txbxContent'))

def bparas(box):
    return box.findall('.//' + q('p'))

def in_txbx(el):
    p = el.getparent()
    while p is not None:
        if p.tag == q('txbxContent'):
            return True
        p = p.getparent()
    return False

# ---------------------------------------------------------------- per-box fillers
def fill_title(b, L):
    p = bparas(b)[0]
    set_para(p, L['title'])
    set_sz(p, 28)                                     # shrink 28pt -> 14pt so the long title fits the box

def fill_info(b, L):
    p = bparas(b)
    set_para(p[0], L['code_master'])
    set_para(p[1], L['author_label'] + L['authors'][0])
    set_para(p[2], L['authors'][1])
    set_para(p[3], L['supervisor_label'] + L['supervisor'])
    set_para(p[4], '')
    set_para(p[5], L['promo_label'] + L['promo'])

def fill_keywords(b, L):
    p = bparas(b)
    set_para(p[0], L['keywords_label'])
    set_para(p[1], L['keywords'])
    if len(p) > 2:
        set_para(p[2], '')

def fill_resume(b, L):
    p = bparas(b)
    set_para(p[0], L['resume_header'])
    set_para(p[1], L['resume'])
    for q_ in p[2:-1]:
        set_para(q_, '')

def fill_objectives(b, L):
    p = bparas(b)
    set_para(p[0], L['obj_header'])
    for i, item in enumerate(L['objectives']):      # box auto-numbers (1. 2. ...), no bullet prefix
        set_para(p[2 + i], item)
        set_sz(p[2 + i], 30)                        # 20pt -> 15pt so all five items fit the box

def fill_defs(b, L):
    p = bparas(b)
    set_para(p[0], L['def1_q'])
    set_para(p[1], L['def1_a'])
    for j in (2, 3, 4):
        set_para(p[j], '')
    set_para(p[5], L['def2_q'])
    set_para(p[6], L['def2_a'])
    for j in (7, 8, 9):
        set_para(p[j], '')

def fill_synthese(b, L):
    p = bparas(b)
    for i, line in enumerate(L['synthese']):
        strip_numpr(p[i]); set_para(p[i], '•  ' + line)   # some paras carry a stray list dash
    for q_ in p[len(L['synthese']):-1]:
        set_para(q_, '')

def fill_refs(b, L):
    p = bparas(b)
    for i in range(5):
        set_para(p[i], REFS[i])
    for q_ in p[5:-1]:
        set_para(q_, '')

def fill_cap1(b, L):
    set_para(bparas(b)[0], L['fig1_caption'])

def fill_cap2(b, L):
    set_para(bparas(b)[0], L['fig2_caption'])

def fill_clear(b, L):
    set_para(bparas(b)[0], '')

def classify(b):
    """map a text box to a filler by the signature of its paragraphs."""
    p = bparas(b)
    s0 = ptext(p[0]).strip()
    allt = ' '.join(ptext(x) for x in p)
    if s0.startswith('Intitul'):
        return fill_title
    if s0.startswith('Figure 1'):
        return fill_cap1
    if s0.startswith('Figure 2'):
        return fill_cap2
    if 'principes des IHMs' in s0:
        return fill_clear
    if 'Interaction Homme Machine (IHM)' in allt and 'Intelligence Artificielle (IA)' in allt:
        return fill_defs
    if s0.startswith('Contexte et Objectifs'):
        return fill_objectives
    if s0.startswith('Mots'):
        return fill_keywords
    if s0 in ('Résumé', 'Resume'):
        return fill_resume
    if s0.startswith('Code Master'):
        return fill_info
    if s0.startswith('Kolski'):
        return fill_refs
    if is_dots(s0) and any('- 7 -' in ptext(x) for x in p):   # synthèse content block
        return fill_synthese
    return None

# ---------------------------------------------------------------- body content
def fill_body(root, L):
    body_paras = [p for p in root.iter(q('p')) if not in_txbx(p)]
    state = None; idx = 0
    for p in body_paras:
        t = ptext(p).strip()
        if 'intersection' in t.lower():                       # section divider
            set_para(p, L['section_header']); state = None; continue
        if t in ('Synthèse', 'Synthese', 'Synthése'):         # synthèse section header
            set_para(p, L['synthese_header']); state = None; continue
        if 'Contribution des IHMs' in t and not is_dots(t):   # check 'des' BEFORE 'de' (substring trap)
            set_para(p, L['col2_header']); state = 'c2'; idx = 0; continue
        if 'Contribution de' in t and 'IHMs' in t and not is_dots(t):
            set_para(p, L['col1_header']); state = 'c1'; idx = 0; continue
        if t.startswith('Référence') or t.startswith('Reference'):
            set_para(p, L['refs_header']); state = None; continue
        if is_dots(t):
            lines = L['col1_lines'] if state == 'c1' else L['col2_lines'] if state == 'c2' else None
            if lines is not None:
                set_para(p, '•  ' + lines[idx] if idx < len(lines) else '')
                idx += 1
            continue

# ---------------------------------------------------------------- build
def build(L, out):
    raw = zipfile.ZipFile(SRC).read('word/document.xml')
    root = etree.fromstring(raw)
    for b in boxes(root):
        f = classify(b)
        if f:
            f(b, L)
    fill_body(root, L)
    new_doc = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)

    with zipfile.ZipFile(SRC) as zin:
        names = zin.namelist()
        with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zout:
            for n in names:
                if n == 'word/document.xml':
                    zout.writestr(n, new_doc)
                elif n == 'word/media/image7.jpeg':
                    zout.writestr(n, FIG1)
                elif n == 'word/media/image8.jpeg':
                    zout.writestr(n, FIG2)
                else:
                    zout.writestr(n, zin.read(n))
    print('saved', out)

build(FR, 'PosterMaster_FR.docx')
build(EN, 'PosterMaster_EN.docx')
