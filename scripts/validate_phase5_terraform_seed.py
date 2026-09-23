"""Generate and Terraform-validate every trusted Phase 5 product candidate stage."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess, sys, tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from phase5_terraform_control import assemble
def run(stage,uri):
    with tempfile.TemporaryDirectory(prefix="resilio-p5-") as td:
        root=Path(td);candidate=root/"candidate.json"
        candidate.write_text(json.dumps({"contract":"resilio-product-terraform-candidate/v1",
            "stage":stage,"processor_uri":uri,
            "processor_verification_comment_id":"1" if stage=="routing" else None},
            separators=(",",":"))+"\n",encoding="utf-8")
        work=root/"work";assemble(ROOT,candidate,work)
        subprocess.run(["terraform",f"-chdir={work}","init","-backend=false","-input=false","-lockfile=readonly"],
                       check=True,stdout=subprocess.DEVNULL)
        subprocess.run(["terraform",f"-chdir={work}","validate"],check=True,stdout=subprocess.DEVNULL)
def main():
    run("empty",None);run("base",None);run("routing","https://resilio-processor-abc-uc.a.run.app")
    print("Phase 5 trusted product Terraform configurations validate.")
if __name__=="__main__": main()
