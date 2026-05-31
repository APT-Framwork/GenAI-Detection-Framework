# -*- coding: utf-8 -*-
"""Fill the ESI Master poster canvas from the State-of-the-Art report.
Produces PosterMaster_FR.pptx and PosterMaster_EN.pptx."""
from pptx import Presentation
from pptx.util import Cm, Pt
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN
from PIL import Image

SRC = '4. Annexe 2_Canevas PosterMaster.pptx'

# ---------------------------------------------------------------- figures
def pad(path, ratio, bg, out):
    im = Image.open(path).convert('RGB')
    w, h = im.size
    if w / h < ratio:                      # need wider canvas
        nw = int(round(h * ratio)); c = Image.new('RGB', (nw, h), bg); c.paste(im, ((nw - w) // 2, 0))
    else:                                  # need taller canvas
        nh = int(round(w / ratio)); c = Image.new('RGB', (w, nh), bg); c.paste(im, (0, (nh - h) // 2))
    c.save(out); return out

FIG1 = pad('figures/The 7 Steps -ckc.png', 13.19 / 7.41, (0, 0, 0), '/tmp/fig1_ckc.png')
FIG2 = pad('figures/ml_domain.png',        12.71 / 4.40, (255, 255, 255), '/tmp/fig2_ml.png')
FIG1B = open(FIG1, 'rb').read()
FIG2B = open(FIG2, 'rb').read()

# ---------------------------------------------------------------- helpers
def get(sl, path):
    parts = [int(x) for x in path.split('.')]
    sh = sl.shapes[parts[0]]
    for p in parts[1:]:
        sh = sh.shapes[p]
    return sh

def set_para(p, text):
    runs = p.runs
    if not runs:
        r = p.add_run(); r.text = text; return r
    runs[0].text = text
    for r in runs[1:]:
        r.text = ''
    return runs[0]

def set_body(tf, idx, lines, size, prefix='•  '):
    p = tf.paragraphs[idx]
    r0 = set_para(p, prefix + lines[0]); r0.font.size = Pt(size)
    for line in lines[1:]:
        np = tf.add_paragraph(); r = np.add_run(); r.text = prefix + line; r.font.size = Pt(size)

def replace_pic(sl, path, blob):
    pic = get(sl, path)
    part = sl.part.related_parts[pic._element.blip_rId]
    part._blob = blob

# ---------------------------------------------------------------- content
from poster_content import FR, EN, REFS

# ---------------------------------------------------------------- fill
def fill(L, out):
    prs = Presentation(SRC); sl = prs.slides[0]

    # Title (widen to the yellow bar, center, 20pt)
    bar = get(sl, '9')
    bl, bt, bw, bh = bar.left, bar.top, bar.width, bar.height
    t = get(sl, '10'); tp = t.text_frame.paragraphs[0]
    r = set_para(tp, L['title']); r.font.size = Pt(20); r.font.bold = True
    tp.alignment = PP_ALIGN.CENTER
    t.left, t.top, t.width, t.height = bl + Cm(1), bt, bw - Cm(2), bh
    t.text_frame.word_wrap = True
    set_para(bar.text_frame.paragraphs[0], '')           # clear 'nn'
    set_para(get(sl, '0.0').text_frame.paragraphs[0], '')  # clear 'IHMIAIU'

    # Info box 21.1
    ib = get(sl, '21.1').text_frame
    set_para(ib.paragraphs[0], L['code_master'])
    p1 = ib.paragraphs[1].runs
    p1[0].text = L['author_label']; p1[1].text = ''; p1[2].text = L['authors'][0]
    p1[3].text = ''; p1[4].text = L['authors'][1]
    p2 = ib.paragraphs[2].runs
    p2[0].text = L['supervisor_label']; p2[1].text = ''; p2[2].text = L['supervisor']
    for r in ib.paragraphs[3].runs:
        r.text = ''
    p4 = ib.paragraphs[4].runs
    p4[0].text = L['promo_label']; p4[1].text = L['promo']

    # Keywords 20
    kw = get(sl, '20').text_frame
    kw.paragraphs[0].runs[0].text = L['keywords_label']
    if len(kw.paragraphs[0].runs) > 1:
        kw.paragraphs[0].runs[1].text = ''
    r = set_para(kw.paragraphs[1], L['keywords']); r.font.size = Pt(14)

    # Objectives 19.0
    ob = get(sl, '19.0').text_frame
    set_para(ob.paragraphs[0], L['obj_header'])
    for i, item in enumerate(L['objectives']):
        r = set_para(ob.paragraphs[2 + i], item); r.font.size = Pt(16)

    # Resume 18.0.2 (single paragraph, clear the rest)
    rb = get(sl, '18.0.2').text_frame
    set_para(rb.paragraphs[0], L['resume'])
    for p in rb.paragraphs[1:]:
        set_para(p, '')
    set_para(get(sl, '18.0.1').text_frame.paragraphs[0], L['resume_header'])

    # Definition boxes  (15 = top = APT, 11 = bottom = CKC)
    d1 = get(sl, '15').text_frame; set_para(d1.paragraphs[0], L['def1_q']); set_para(d1.paragraphs[1], L['def1_a'])
    d2 = get(sl, '11').text_frame; set_para(d2.paragraphs[0], L['def2_q']); set_para(d2.paragraphs[1], L['def2_a'])

    # Section heading + columns
    sh = set_para(get(sl, '16').text_frame.paragraphs[0], L['section_header']); sh.font.size = Pt(24)
    c1 = get(sl, '17.0').text_frame; set_para(c1.paragraphs[0], L['col1_header']); set_body(c1, 1, L['col1_lines'], 14)
    c2 = get(sl, '17.1').text_frame; set_para(c2.paragraphs[0], L['col2_header']); set_body(c2, 1, L['col2_lines'], 14)

    # Synthese
    sy = get(sl, '22').text_frame
    for i, b in enumerate(L['synthese']):
        set_para(sy.paragraphs[i], b)
    set_para(get(sl, '23').text_frame.paragraphs[0], L['synthese_header'])

    # References
    rf = get(sl, '24.0').text_frame
    for i in range(5):
        set_para(rf.paragraphs[i], REFS[i])
    for p in rf.paragraphs[5:]:
        set_para(p, '')
    set_para(get(sl, '24.1').text_frame.paragraphs[0], L['refs_header'])

    # Captions + figures
    set_para(get(sl, '25').text_frame.paragraphs[0], L['fig1_caption'])
    set_para(get(sl, '26.0').text_frame.paragraphs[0], L['fig2_caption'])
    replace_pic(sl, '12', FIG1B)
    replace_pic(sl, '26.1', FIG2B)

    prs.save(out)
    print('saved', out)

fill(FR, 'PosterMaster_FR.pptx')
fill(EN, 'PosterMaster_EN.pptx')
