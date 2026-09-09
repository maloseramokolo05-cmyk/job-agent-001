from __future__ import annotations
import re
WEIGHTS={"role_title":15,"required_skills":20,"experience":15,"education":10,"location":10,"work_arrangement":5,"salary":5,"language":5,"industry":5,"seniority":5,"portfolio_technical":5}
STOP={"and","the","with","for","from","you","your","our","this","that","will","are","job","role","work","team","required","experience"}
def terms(value):
 if isinstance(value,list):value=" ".join(str(x) for x in value)
 if isinstance(value,dict):value=" ".join(str(x) for x in value.values())
 return {x for x in re.findall(r"[a-z0-9+#.]{2,}",str(value).lower()) if x not in STOP}
def ratio(required,factual):return min(1,len(required&factual)/max(1,min(8,len(required))))
def classify(score):return "Excellent Match" if score>=90 else "Strong Match" if score>=80 else "Good Match" if score>=70 else "Possible Match" if score>=60 else "Low Priority"
def score_job(job,profile,preferences,cv_text=""):
 title=terms(job.get("title",""));requirements=terms(job.get("requirements","") or job.get("description",""));body=title|requirements;skills=terms(profile.get("skills",[]))|terms(profile.get("tools",[]));experience=terms(profile.get("experience",[]))|terms(cv_text);education=terms(profile.get("education",[]));languages=terms(profile.get("languages",[]));targets=terms(profile.get("target_roles",[]))|terms(preferences.get("job_categories",[]));all_facts=skills|experience|education|languages
 hard=[]
 if any(x in requirements for x in {"citizen","citizenship","permit","visa"}) and not profile.get("work_authorization"):hard.append("Work authorization requirement is unverified")
 values={"role_title":ratio(title,targets|experience),"required_skills":ratio(requirements,skills),"experience":ratio(requirements,experience),"education":1 if not requirements&{"degree","diploma","bachelor","master"} else ratio(requirements&{"degree","diploma","bachelor","master"},education),"location":1 if any(x.lower() in job.get("location","").lower() for x in preferences.get("priority_locations",[])) else .5 if not job.get("location") else .2,"work_arrangement":1 if not job.get("work_mode") or job.get("work_mode","").lower() in terms(profile.get("work_preferences",[])) else .4,"salary":1 if not job.get("salary") else .6,"language":1 if not requirements&{"english","afrikaans","zulu","sotho"} else ratio(requirements&{"english","afrikaans","zulu","sotho"},languages),"industry":ratio(body,targets) if targets else .5,"seniority":1 if not body&{"senior","lead","director","head"} else ratio(body&{"senior","lead","director","head"},experience),"portfolio_technical":1 if not body&{"portfolio","github"} else 1 if profile.get("portfolio") or profile.get("github") else 0}
 breakdown={key:round(values[key]*weight,1) for key,weight in WEIGHTS.items()};score=round(sum(breakdown.values()),1);missing=sorted(requirements-all_facts,key=lambda x:(-len(x),x))[:15];positive=sorted(requirements&all_facts)[:15];concerns=list(hard)
 if missing:concerns.append(f"{len(missing)} requirement terms are not verified")
 return {"score":score,"classification":classify(score),"must_have":{"passed":not hard,"unverified":hard},"breakdown":breakdown,"missing_requirements":missing,"positive_evidence":positive,"risk_flags":concerns,"reasoning":f"Factual match score {score}/100 (not a hiring probability). Strongest verified dimensions: "+", ".join(sorted(breakdown,key=breakdown.get,reverse=True)[:3])+"."}
