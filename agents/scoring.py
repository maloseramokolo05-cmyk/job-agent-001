from __future__ import annotations
import re
WEIGHTS={"skills":30,"experience":20,"education":15,"location":10,"seniority":10,"salary":5,"industry":5,"keywords":5}
STOP={"and","the","with","for","from","you","your","our","this","that","will","are","job","role"}
def terms(value):
 if isinstance(value,list): value=" ".join(str(x) for x in value)
 if isinstance(value,dict): value=" ".join(str(x) for x in value.values())
 return {x for x in re.findall(r"[a-z0-9+#.]{2,}",str(value).lower()) if x not in STOP}
def ratio(required, factual): return min(1, len(required & factual)/max(1,min(8,len(required))))
def classify(score):
 return "Excellent Match" if score>=90 else "Strong Match" if score>=80 else "Good Match" if score>=70 else "Possible Match" if score>=60 else "Low Priority"
def score_job(job:dict, profile:dict, preferences:dict, cv_text=""):
 body=terms(job.get("title","")+" "+job.get("description","")+" "+job.get("requirements","")); facts=terms(cv_text)|terms(profile.get("skills",[]))|terms(profile.get("experience",[]))|terms(profile.get("education",[]))
 skills=ratio(body, facts); exp=ratio(terms(job.get("requirements","")), facts); edu=1 if not any(x in body for x in {"degree","diploma","bachelor","master"}) else ratio(body & {"degree","diploma","bachelor","master"},facts)
 loc=1 if any(x.lower() in job.get("location","").lower() for x in preferences.get("priority_locations",[])) or "remote" in job.get("work_mode","").lower() else .35
 senior_terms={"senior","lead","manager","director","head"}; senior=1 if not (body&senior_terms) else ratio(body&senior_terms,facts)
 salary=1 if not job.get("salary") or not profile.get("salary_expectations") else .75
 industry=ratio(terms(preferences.get("job_categories",[])),body) if preferences.get("job_categories") else ratio(facts,body)
 keywords=ratio(body,facts)
 raw={"skills":skills,"experience":exp,"education":edu,"location":loc,"seniority":senior,"salary":salary,"industry":industry,"keywords":keywords}
 breakdown={k:round(raw[k]*w,1) for k,w in WEIGHTS.items()}; total=round(sum(breakdown.values()),1)
 missing=sorted(body-facts, key=lambda x:(-len(x),x))[:12]
 return {"score":total,"classification":classify(total),"breakdown":breakdown,"missing_requirements":missing,"reasoning":f"Deterministic factual overlap score: {total}/100; strongest dimensions are "+", ".join(sorted(breakdown,key=breakdown.get,reverse=True)[:3])+"."}
