import json
import yaml
import pathlib


def literal_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")

yaml.add_representer(str, literal_representer)

def json2yaml(jsonf: pathlib.Path):
    with open(jsonf, "r", encoding="utf-8") as f:
        d = json.load(f)
    newname = jsonf.name.removesuffix(".json") + ".yml"
    with open(pathlib.Path(jsonf.parent / newname), "w", encoding="utf-8") as f:
        yaml.dump(d, f, sort_keys=False, allow_unicode=True)
    jsonf.unlink()


for f in pathlib.Path(".").rglob("**.json"):
    if f.is_dir():
        continue
    json2yaml(f)