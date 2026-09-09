from pathlib import Path
from docx import Document
from pypdf import PdfReader
def parse_cv(path: str|Path) -> str:
 p=Path(path)
 if not p.exists(): raise FileNotFoundError(f"Master CV not found: {p}")
 if p.suffix.lower()==".pdf": return "\n".join(page.extract_text() or "" for page in PdfReader(p).pages).strip()
 if p.suffix.lower()==".docx": return "\n".join(x.text for x in Document(p).paragraphs if x.text.strip()).strip()
 raise ValueError("CV must be PDF or DOCX")
def find_master(root:Path):
 for name in ("master_cv.docx","master_cv.pdf"):
  if (root/name).exists(): return root/name
 return None
