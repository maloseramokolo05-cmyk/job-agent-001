from __future__ import annotations
import hashlib,re
from datetime import date
from pathlib import Path
from docx import Document
from docx.shared import Pt
from backend.config import ROOT
from backend.database import connect,now
GENERATOR_VERSION="2.0.0"; TEMPLATE_VERSION="ats-mobile-1"
def safe(value): return re.sub(r"[^A-Za-z0-9_-]+","_",value).strip("_")[:70]
def facts(profile,cv_text): return [line.strip() for line in cv_text.splitlines() if line.strip()] or [profile.get("name","Candidate")]
def record(job_id,kind,path,master):
 digest=hashlib.sha256(master.encode()).hexdigest(); content=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
 with connect() as db: db.execute("INSERT INTO documents(job_id,document_type,local_path,created_at,master_cv_hash,template_version,generator_version,content_hash) VALUES(?,?,?,?,?,?,?,?)",(job_id,kind,path,now(),digest,TEMPLATE_VERSION,GENERATOR_VERSION,content))
def generate_cv(job,profile,cv_text,job_id=None):
 if not cv_text.strip():raise ValueError("A non-empty master CV is required; documents are never fabricated")
 stem=f"{date.today().isoformat()}_{safe(job['company'])}_{safe(job['title'])}_{safe(profile['name'])}_CV";out=ROOT/"generated_cvs";out.mkdir(exist_ok=True);path=out/f"{stem}.docx";doc=Document();style=doc.styles["Normal"];style.font.name="Arial";style.font.size=Pt(10);doc.add_heading(profile["name"],0);contacts=" | ".join(x for x in [profile.get("email"),profile.get("phone"),profile.get("location"),profile.get("linkedin")] if x);doc.add_paragraph(contacts);doc.add_heading("Professional Profile",1);doc.add_paragraph(f"Application focus: {job['title']} at {job['company']}. All experience and qualifications below originate in the master CV.");doc.add_heading("Relevant Skills and Experience",1)
 terms={x.lower() for x in re.findall(r"[A-Za-z][A-Za-z+#.-]{2,}",f"{job.get('title','')} {job.get('requirements','')} {job.get('description','')}")}; ordered=sorted(facts(profile,cv_text),key=lambda line:sum(word in line.lower() for word in terms),reverse=True)
 for line in ordered:doc.add_paragraph(line,style="List Bullet" if len(line)<180 else None)
 doc.save(path);relative=str(path.relative_to(ROOT));pdf=None
 try:
  from reportlab.lib.pagesizes import A4
  from reportlab.pdfgen.canvas import Canvas
  pdfpath=out/f"{stem}.pdf";canvas=Canvas(str(pdfpath),pagesize=A4);y=800
  for line in [profile["name"],contacts]+ordered:
   for chunk in [line[i:i+105] for i in range(0,len(line),105)] or [""]:
    if y<50:canvas.showPage();y=800
    canvas.drawString(45,y,chunk);y-=14
  canvas.save();pdf=str(pdfpath.relative_to(ROOT))
 except (ImportError,OSError): pass
 if job_id:record(job_id,"CV",relative,cv_text); record(job_id,"CV_PDF",pdf,cv_text) if pdf else None
 return relative,pdf
def generate_cover_letter(job,profile,cv_text,job_id=None):
 if not cv_text.strip():raise ValueError("A master CV is required")
 stem=f"{date.today().isoformat()}_{safe(job['company'])}_{safe(job['title'])}_{safe(profile['name'])}_Cover_Letter.docx";path=ROOT/"cover_letters"/stem;doc=Document();doc.add_paragraph(profile["name"]);doc.add_paragraph("Dear Hiring Team,");doc.add_paragraph(f"I am applying for the {job['title']} opportunity at {job['company']}. My interest is grounded in the experience and skills documented in my attached CV.");evidence=" ".join(facts(profile,cv_text)[:4])[:700];doc.add_paragraph(f"Relevant background: {evidence}");doc.add_paragraph("I would welcome the opportunity to discuss how this factual background aligns with your requirements.");doc.add_paragraph(f"Kind regards,\n{profile['name']}");doc.save(path);relative=str(path.relative_to(ROOT));record(job_id,"COVER_LETTER",relative,cv_text) if job_id else None;return relative
