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
FR = dict(
    title="État de l'Art sur la Détection des Attaques APT Multi-Étapes par Apprentissage Automatique à l'aide de la Cyber Kill Chain",
    code_master="Code Master : ……",
    author_label="Nom & Prénom : ", authors=("KASSOUSSI Oussama Mehdi", "NAOUI Yacine"),
    supervisor_label="Encadré par : ", supervisor="Pr. Abdelouahid Derhab",
    promo_label="Promotion : ", promo="2025 / 2026",
    keywords_label="Mots clés : ",
    keywords="APT, Cyber Kill Chain, MITRE ATT&CK, Apprentissage automatique, Apprentissage profond, IA générative, Détection d'intrusion",
    obj_header="Contexte et Objectifs :",
    objectives=[
        "Définir les APT et leur nature multi-étapes.",
        "Présenter la Cyber Kill Chain et MITRE ATT&CK.",
        "Analyser les menaces 2024–2025 et le rôle dual de l'IA.",
        "Étudier de façon critique les jeux de données d'APT.",
        "Comparer les approches ML, Deep Learning et IA générative.",
    ],
    resume_header="Résumé",
    resume="Les menaces persistantes avancées (APT) figurent parmi les cyberattaques les plus dangereuses : "
           "furtives, persistantes et déroulées en plusieurs étapes coordonnées. Cet état de l'art étudie leur "
           "détection par apprentissage automatique, structurée autour de la Cyber Kill Chain et de MITRE ATT&CK. "
           "Il dresse le paysage des menaces de 2024–2025, où l'IA générative est exploitée à chaque étape de la "
           "chaîne d'attaque, puis mène une étude critique des jeux de données et des solutions ML, Deep Learning "
           "et IA générative. La synthèse montre qu'aucune approche unique ne traite à la fois la séquentialité "
           "temporelle, la rareté des données étiquetées et le passage à l'échelle réel.",
    def1_q="Qu'est-ce qu'une Menace Persistante Avancée (APT) ?",
    def1_a="Une cyberattaque ciblée, furtive et prolongée, menée par un adversaire organisé et bien doté "
           "(souvent étatique), qui progresse lentement à travers plusieurs étapes pour exfiltrer des données ou "
           "nuire à une organisation tout en restant indétecté.",
    def2_q="Qu'est-ce que la Cyber Kill Chain (CKC) ?",
    def2_a="Un modèle de Lockheed Martin décomposant une attaque en sept phases — reconnaissance, armement, "
           "livraison, exploitation, installation, commande & contrôle, actions sur objectifs — pour la détecter "
           "et l'interrompre avant son objectif final.",
    section_header="Solutions de Détection des APT",
    col1_header="Classification des solutions",
    col1_lines=[
        "ML traditionnel : Random Forest, SVM — solides mais sans modélisation séquentielle.",
        "Deep Learning : CNN, LSTM, GNN, Transformers — capturent les motifs temporels et structurels.",
        "IA générative : auto-encodeurs, VAE, agents RL — détection non supervisée et adaptative.",
    ],
    col2_header="Constats clés",
    col2_lines=[
        "Les méthodes par graphes (GNN) sont les plus alignées sur le comportement des APT (mouvement latéral).",
        "Aucun modèle ne couvre à la fois temporalité, données non étiquetées et passage à l'échelle.",
        "Les jeux de données APT annotés CKC/MITRE restent rares (Linux-APT-2024, KAPT-2024, CICAPT-IIoT).",
        "Voie d'avenir : combiner cadres structurés, modèles séquentiels/graphes et composants génératifs.",
    ],
    synthese_header="Synthèse",
    synthese=[
        "Les APT exigent une détection multi-étapes, guidée par la Cyber Kill Chain et MITRE ATT&CK.",
        "En 2024–2025, les APT deviennent « augmentées par l'IA » : reconnaissance, phishing et malwares automatisés.",
        "Le ML traditionnel reste un socle, mais peine face à la nature séquentielle des APT.",
        "Le Deep Learning (surtout les GNN) et l'IA générative offrent les pistes les plus prometteuses.",
        "L'avenir de la détection réside dans la combinaison de ces approches, et non dans un modèle unique.",
    ],
    refs_header="Références bibliographiques",
    fig1_caption="Figure 1 : Les sept phases de la Cyber Kill Chain (CKC)",
    fig2_caption="Figure 2 : Les paradigmes de l'apprentissage automatique",
)

EN = dict(
    title="State of the Art Study on Machine-Learning-Based Detection of Multi-Stage APT Attacks using the Cyber Kill Chain",
    code_master="Master Code: ……",
    author_label="Name & Surname: ", authors=("KASSOUSSI Oussama Mehdi", "NAOUI Yacine"),
    supervisor_label="Supervised by: ", supervisor="Pr. Abdelouahid Derhab",
    promo_label="Academic Year: ", promo="2025 / 2026",
    keywords_label="Keywords: ",
    keywords="APT, Cyber Kill Chain, MITRE ATT&CK, Machine Learning, Deep Learning, Generative AI, Intrusion Detection",
    obj_header="Context and Objectives:",
    objectives=[
        "Define APTs and their multi-stage nature.",
        "Present the Cyber Kill Chain and MITRE ATT&CK.",
        "Analyze the 2024–2025 threat landscape and AI's dual role.",
        "Critically study existing APT detection datasets.",
        "Compare ML, Deep Learning and Generative AI approaches.",
    ],
    resume_header="Abstract",
    resume="Advanced Persistent Threats (APTs) are among the most dangerous cyberattacks: stealthy, persistent "
           "and unfolding across several coordinated stages. This state-of-the-art study reviews their detection "
           "through machine learning, structured around the Cyber Kill Chain and MITRE ATT&CK. It maps the "
           "2024–2025 threat landscape, where Generative AI is weaponized at every stage of the kill chain, then "
           "critically studies the available datasets and the ML, Deep Learning and Generative AI solutions. The "
           "synthesis shows that no single approach jointly handles temporal sequencing, labeled-data scarcity and "
           "real-world scalability.",
    def1_q="What is an Advanced Persistent Threat (APT)?",
    def1_a="A targeted, stealthy and prolonged cyberattack carried out by a well-resourced, organized adversary "
           "(often state-sponsored) that advances slowly through multiple stages to exfiltrate data or harm an "
           "organization while remaining undetected.",
    def2_q="What is the Cyber Kill Chain (CKC)?",
    def2_a="A Lockheed Martin model that breaks an attack into seven phases — reconnaissance, weaponization, "
           "delivery, exploitation, installation, command & control, actions on objectives — to detect and "
           "disrupt it before its final goal.",
    section_header="APT Detection Solutions",
    col1_header="Classification of solutions",
    col1_lines=[
        "Traditional ML: Random Forest, SVM — strong baselines but no sequential modeling.",
        "Deep Learning: CNN, LSTM, GNN, Transformers — capture temporal and structural patterns.",
        "Generative AI: autoencoders, VAEs, RL agents — unsupervised, adaptive detection.",
    ],
    col2_header="Key findings",
    col2_lines=[
        "Graph-based methods (GNN) are the most aligned with APT behavior (lateral movement).",
        "No single model jointly covers temporality, unlabeled data and scalability.",
        "APT datasets mapped to CKC/MITRE remain scarce (Linux-APT-2024, KAPT-2024, CICAPT-IIoT).",
        "Way forward: combine structured frameworks, sequential/graph models and generative components.",
    ],
    synthese_header="Summary",
    synthese=[
        "APTs require multi-stage detection, guided by the Cyber Kill Chain and MITRE ATT&CK.",
        "In 2024–2025, APTs become 'AI-augmented': automated reconnaissance, phishing and polymorphic malware.",
        "Traditional ML remains a baseline but struggles with the sequential nature of APTs.",
        "Deep Learning (especially GNNs) and Generative AI offer the most promising directions.",
        "The future of detection lies in combining these approaches, not in any single model.",
    ],
    refs_header="References",
    fig1_caption="Figure 1: The seven phases of the Cyber Kill Chain (CKC)",
    fig2_caption="Figure 2: Machine-learning paradigms for APT detection",
)

REFS = [
    "[1] Tatam, M. et al. (2021). A review of threat modelling approaches for APT-style attacks. Heliyon, 7(1).",
    "[2] Krishnapriya, S. & Singh, S. (2024). A Comprehensive Survey on APT Detection Techniques. CMES.",
    "[3] Singh, S. et al. (2016). A comprehensive study on APT attacks and countermeasures. J. Supercomputing.",
    "[4] Karim, O. et al. (2024). APT & Intrusion Detection Evaluation Dataset for Linux Systems 2024. Data in Brief.",
    "[5] Jiang, Y. et al. (2025). MITRE ATT&CK Applications in Cybersecurity and the Way Forward. arXiv:2502.10825.",
]

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
