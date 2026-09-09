from __future__ import annotations
import re
from pathlib import Path
from docx import Document
from docx.shared import Pt
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas
from backend.config import ROOT
def safe(s): return re.sub(r"[^A-Za-z0-9_-]+","_",s).strip("_")[:70]
def _facts(profile, cv_text):
 lines=[x.strip() for x in cv_text.splitlines() if x.strip()]
 return lines or [profile.get("name","Candidate"), profile.get("location","")]
def generate_cv(job, profile, cv_text):
 if not cv_text.strip(): raise ValueError("A non-empty master CV is required; documents are never fabricated")
 stem=f"{safe(job['company'])}_{safe(job['title'])}_{safe(profile['name'])}_CV"; out=ROOT/"generated_cvs"; out.mkdir(exist_ok=True)
 path=out/f"{stem}.docx"; doc=Document(); style=doc.styles["Normal"]; style.font.name="Arial"; style.font.size=Pt(10)
 doc.add_heading(profile["name"],0); contacts=" | ".join(x for x in [profile.get("email"),profile.get("phone"),profile.get("location"),profile.get("linkedin")] if x); doc.add_paragraph(contacts)
 doc.add_heading("Professional Profile",1); doc.add_paragraph(f"Candidate profile tailored for {job['title']} at {job['company']}. The factual experience and qualifications below are reproduced from the master CV.")
 doc.add_heading("Master CV Information",1)
 for line in _facts(profile,cv_text): doc.add_paragraph(line, style="List Bullet" if len(line)<180 else None)
 doc.save(path); pdf=out/f"{stem}.pdf"; c=Canvas(str(pdf),pagesize=A4); y=800
 for line in [profile["name"],contacts,"",f"Target role: {job['title']} — {job['company']}"]+_facts(profile,cv_text):
  for chunk in [line[i:i+105] for i in range(0,len(line),105)] or [""]:
   if y<50: c.showPage(); y=800
   c.drawString(45,y,chunk); y-=14
 c.save(); return str(path.relative_to(ROOT)),str(pdf.relative_to(ROOT))
def generate_cover_letter(job, profile, cv_text):
 if not cv_text.strip(): raise ValueError("A master CV is required")
 stem=f"{safe(job['company'])}_{safe(job['title'])}_{safe(profile['name'])}_Cover_Letter.docx"; path=ROOT/"cover_letters"/stem
 doc=Document(); doc.add_paragraph(profile["name"]); doc.add_paragraph("Dear Hiring Team,"); doc.add_paragraph(f"I am applying for the {job['title']} opportunity at {job['company']}. My interest is grounded in the experience and skills documented in my attached CV.")
 evidence=" ".join(_facts(profile,cv_text)[:4])[:700]; doc.add_paragraph(f"Relevant background: {evidence}")
 doc.add_paragraph("I would welcome the opportunity to discuss how this factual background aligns with your requirements."); doc.add_paragraph(f"Kind regards,\n{profile['name']}"); doc.save(path); return str(path.relative_to(ROOT))
