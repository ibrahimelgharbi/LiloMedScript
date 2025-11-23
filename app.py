import os
import tempfile

import streamlit as st
from pptx import Presentation
from openai import OpenAI

# -------------------------
# CONFIG STREAMLIT
# -------------------------
st.set_page_config(
    page_title="LiloMedScript – Transcription & Résumé audio médical",
    page_icon="🎧",
    layout="wide"
)

# Affichage du logo + titre
logo_path = "lilomedscript_logo.png"  # à mettre dans le repo
if os.path.exists(logo_path):
    col_logo, col_title = st.columns([1, 4])
    with col_logo:
        st.image(logo_path, width=80)
    with col_title:
        st.title("LiloMedScript")
else:
    st.title("LiloMedScript")

st.write(
    "🎧 Application de transcription et de synthèse d'audios médicaux.\n\n"
    "Uploade un audio (conférence, staff, cours...) puis choisis le type de sortie : "
    "**Transcription complète**, **Résumé & points clés**, ou **Slides PowerPoint**."
)

st.markdown("---")

# -------------------------
# CONFIG OPENAI (API KEY VIA SECRETS)
# -------------------------
# Dans Streamlit Cloud, tu définiras st.secrets[\"OPENAI_API_KEY\"]
if "OPENAI_API_KEY" not in st.secrets:
    st.error("⚠️ Clé API OpenAI manquante. Ajoute-la dans les secrets Streamlit.")
    st.stop()

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# -------------------------
# FONCTIONS MÉTIERS
# -------------------------
def transcribe_audio(uploaded_file) -> str:
    """
    Transcrit un fichier audio en texte avec gpt-4o-mini-transcribe.
    Les données restent côté OpenAI, Streamlit Cloud gère juste l'interface.
    """
    # On écrit le fichier uploadé dans un fichier temporaire
    suffix = os.path.splitext(uploaded_file.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    with open(tmp_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            # Modèle de transcription optimisé
            model="gpt-4o-mini-transcribe",
            file=audio_file,
            language="fr",  # force le FR, adapte si besoin
        )

    # On supprime le fichier temporaire
    os.remove(tmp_path)

    return transcription.text


def summarize_text(transcript: str) -> str:
    """Produit un résumé structuré de la transcription."""
    prompt = f"""
Tu es un médecin spécialiste qui résume des conférences médicales pour des internes.

Écris un résumé clair et structuré de la conférence ci-dessous.

Contraintes :
- En français.
- Commence par un résumé global en 5–10 lignes.
- Puis une section "Points clés" sous forme de bullet points.
- Puis une section "Implications pratiques pour la clinique" si pertinent (bullet points).
- Style : concis, pédagogique, pas de blabla inutile.

Transcription :
\"\"\"{transcript}\"\"\"
"""

    response = client.responses.create(
        model="gpt-5-nano",  # modèle léger et économique
        input=[
            {
                "role": "user",
                "content": prompt
            }
        ],
    )

    return response.output_text


def generate_slides_markdown(transcript: str) -> str:
    """
    Demande au modèle une structure de diaporama en Markdown.
    """
    prompt = f"""
À partir de cette transcription d'une conférence médicale, propose une structure de diaporama (PowerPoint) en français.

Contraintes :
- Entre 5 et 10 diapositives.
- Format STRICT en Markdown comme ci-dessous :
  # Titre de la présentation
  ## Slide 1 : Titre de la slide
  - Point 1
  - Point 2

  ## Slide 2 : Titre de la slide
  - Point 1
  - Point 2
  etc.

- La première diapositive doit être un titre général (pas de puces).
- Les autres : objectifs, notions clés, physiopathologie, aspects cliniques, traitement, messages à retenir, conclusion.

Transcription :
\"\"\"{transcript}\"\"\"
"""

    response = client.responses.create(
        model="gpt-5-nano",
        input=[
            {
                "role": "user",
                "content": prompt
            }
        ],
    )

    return response.output_text


def markdown_to_pptx(md: str, output_path: str):
    """
    Transforme une structure de slides en Markdown en un fichier PPTX simple.
    """
    prs = Presentation()
    lines = [l.strip() for l in md.splitlines() if l.strip()]

    bullet_frame = None

    for line in lines:
        # Titre principal "# ..."
        if line.startswith("# ") and not line.startswith("##"):
            title_text = line[2:].strip()
            slide = prs.slides.add_slide(prs.slide_layouts[0])  # Titre seul
            slide.shapes.title.text = title_text
            continue

        # Nouvelle slide "## Slide X : Titre"
        if line.startswith("## "):
            slide_title = line[3:].strip()
            slide = prs.slides.add_slide(prs.slide_layouts[1])  # Titre + contenu
            slide.shapes.title.text = slide_title
            body = slide.placeholders[1]
            bullet_frame = body.text_frame
            bullet_frame.clear()
            continue

        # Bullet "- point"
        if line.startswith("- "):
            bullet_text = line[2:].strip()
            if bullet_frame is not None:
                if not bullet_frame.text:
                    bullet_frame.text = bullet_text
                else:
                    p = bullet_frame.add_paragraph()
                    p.text = bullet_text
            continue

    prs.save(output_path)


# -------------------------
# UI STREAMLIT
# -------------------------
uploaded_file = st.file_uploader(
    "Dépose ton fichier audio (mp3, wav, m4a, mp4…)",
    type=["mp3", "wav", "m4a", "mp4"]
)

mode = st.radio(
    "Choisis le type de sortie :",
    [
        "Retranscription complète",
        "Résumé + points clés",
        "Génération de slides (PPTX)"
    ]
)

with st.expander("ℹ️ Conseils pour les audios longs (≈30 minutes)"):
    st.write(
        "- Préfère des fichiers compressés (mp3) plutôt que wav.\n"
        "- Le traitement (transcription + résumé/slides) se fait côté API OpenAI.\n"
        "- Pour des très longues conférences, on pourra ensuite ajouter un découpage en plusieurs morceaux."
    )

if uploaded_file is not None:
    st.audio(uploaded_file, format="audio/mp3")

    if st.button("🚀 Lancer le traitement", type="primary"):
        try:
            with st.spinner("Transcription en cours…"):
                transcript = transcribe_audio(uploaded_file)

            if mode == "Retranscription complète":
                st.subheader("📝 Transcription complète")
                st.text_area("Texte transcrit", transcript, height=400)

                # Fichier texte à télécharger
                txt_path = "LiloMedScript_transcription.txt"
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(transcript)

                with open(txt_path, "rb") as f:
                    st.download_button(
                        "📥 Télécharger la transcription (.txt)",
                        data=f,
                        file_name="LiloMedScript_transcription.txt",
                        mime="text/plain"
                    )

            elif mode == "Résumé + points clés":
                with st.spinner("Génération du résumé…"):
                    summary = summarize_text(transcript)

                st.subheader("🧾 Résumé & points clés")
                st.markdown(summary)

                txt_path = "LiloMedScript_resume_points_cles.txt"
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(summary)

                with open(txt_path, "rb") as f:
                    st.download_button(
                        "📥 Télécharger le résumé (.txt)",
                        data=f,
                        file_name="LiloMedScript_resume_points_cles.txt",
                        mime="text/plain"
                    )

            elif mode == "Génération de slides (PPTX)":
                with st.spinner("Génération de la structure de slides…"):
                    slides_md = generate_slides_markdown(transcript)

                st.subheader("📑 Structure des slides (Markdown généré)")
                st.markdown(slides_md)

                pptx_path = "LiloMedScript_conference_medicale.pptx"
                with st.spinner("Création du fichier PowerPoint…"):
                    markdown_to_pptx(slides_md, pptx_path)

                with open(pptx_path, "rb") as f:
                    st.download_button(
                        "📥 Télécharger le diaporama (.pptx)",
                        data=f,
                        file_name="LiloMedScript_conference_medicale.pptx",
                        mime=(
                            "application/"
                            "vnd.openxmlformats-officedocument.presentationml.presentation"
                        )
                    )

        except Exception as e:
            st.error(f"❌ Erreur lors du traitement : {e}")
else:
    st.info("⬆️ Uploade un fichier audio pour commencer.")
