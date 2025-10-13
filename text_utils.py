#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2025 smithaulait
# <https://github.com/smithaulait>

import json
import pathlib
import os
import subprocess
import sys
import time
import urllib.request

PWD = pathlib.Path(__file__).resolve().parents[0]
CHAPTERS = ["1", "2", "3", "4"]
DUMP_LANGS = ["en", "ja"]
DUMP_URL = "https://raw.githubusercontent.com/HushBugger/hushbugger.github.io/refs/heads/master/deltarune/text"
LANGS = DUMP_LANGS + ["vi"]
BASE_LANG = "en"
L10N_LANG = "vi"
L10N_CHAPTER = "1"

def helpmsg():
    print("view the end of this script for help")
    sys.exit(1)


def echo(strg: str):
    print(f"--> {strg}")


def mkdir(dir):
    pathlib.Path.mkdir(dir, parents=True, exist_ok=True)


def dict2file(in_dict, out_file):
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(in_dict, f, indent=2, ensure_ascii=False)


def file2dict(in_file) -> dict:
    with open(in_file, "r", encoding="utf-8") as f:
        return json.load(f)


def smartsort(k_and_v):
    pieces = k_and_v[0].split("_")
    for i, piece in enumerate(pieces):
        if piece.isdigit():
            # Natsort of integers (particularly line numbers)
            pieces[i] = piece.rjust(16, "0")
    return pieces


def get_textdata(chapter) -> dict:
    master = {
        "pwd": PWD / f"chapter{chapter}",
        "dir": {},
        "jsons_fullpath": {},
        "jsons": {},
    }
    try:
        master["game_dir"] = pathlib.Path(os.environ["DELTARUNE_HOME"])
    except KeyError:
        echo("DELTARUNE_HOME variable not set.")
        pass
    for lang in LANGS:
        master["dir"][lang] = master["pwd"] / lang / "obj"
        mkdir(master["dir"][lang])
        master["jsons_fullpath"][lang] = [i for i in master["dir"][lang].iterdir() if str(i).endswith(".json")]
        master["jsons"][lang] = [i.name for i in master["jsons_fullpath"][lang]]
    return master


def merge_json(jsons: list) -> dict:
    merged = {}
    for j in jsons:
        merged.update(file2dict(j))
    return merged


def split_dump():
    """Process existing json dump and split strings based on position in code"""
    echo("loading raw dumps")
    raw_lang = file2dict(PWD / "common" / "lang.json")
    raw_sourcemap = file2dict(PWD / "common" / "sourcemap.json")
    linedups_map = {n: {} for n in CHAPTERS}
    new_sourcemap = {n: {} for n in CHAPTERS}

    for chapter in CHAPTERS:
        textdata = get_textdata(chapter)

        echo(f"generate: ch{chapter} sourcemap")
        # Track strings whose function was called in the same line in the same code
        # "<code object>:<line position>": <count>, ...
        ch_dup_map = linedups_map[chapter]

        for fileno in raw_sourcemap[chapter].values():
            if fileno not in ch_dup_map:
                ch_dup_map[fileno] = 1
            else:
                ch_dup_map[fileno] += 1

        # Rebuild strings map. This is required to preserve strings order
        # "<code object>": {
        #     "<line position>": "<key>", ...
        # }
        ch_sourcemap = new_sourcemap[chapter]
        dupecount = 0

        for k, v in raw_sourcemap[chapter].items():
            filename, lineno = v.split(":")
            try:
                ch_sourcemap[filename]
            except KeyError:
                ch_sourcemap[filename] = {}

            # sometimes Mr. Toby loves single-line code
            # in this case, we can't guarantee correct sentences order
            if linedups_map[chapter][v] > 1:
                dupecount += 1
                lineno += f"_{dupecount}"
            else:
                dupecount = 0
            ch_sourcemap[filename][lineno] = k

        # sort by line number
        for filename in ch_sourcemap:
            ch_sourcemap[filename] = dict(sorted(ch_sourcemap[filename].items(), key=smartsort))

        dict2file(ch_sourcemap, textdata["pwd"] / "sourcemap.json")

        # Group strings to files based on origin file name
        for lang in DUMP_LANGS:
            echo(f"split: ch{chapter} ({lang}) strings")
            lang_strings = {}

            for filename in new_sourcemap[chapter]:
                obj_file = textdata["dir"][lang] / str(filename.removesuffix(".gml") + ".json")
                obj_strings = {}

                for k in new_sourcemap[chapter][filename].values():
                    try:
                        str_value = raw_lang[chapter][lang][k]
                    except KeyError:
                        print(f"not found: {k}")
                        continue

                    lang_strings[k] = obj_strings[k] = str_value

                if obj_strings == {}:
                    obj_file.unlink(missing_ok=True)
                    continue

                dict2file(obj_strings, obj_file)

            # orphan strings basically exists in original dump but not
            # referenced in the final code. 90% sure they are unused
            lang_orphan = {}
            lang_orphan_file = textdata["dir"][lang] / "orphan.json"

            for k in raw_lang[chapter][lang]:
                if k in lang_strings:
                    continue
                if k == "date":
                    continue
                if f"{k}_DUP" in lang_strings:
                    print(f"{k} is not mapped, but appears to be a duplicate")
                lang_orphan[k] = raw_lang[chapter][lang][k]

            if lang_orphan != {}:
                dict2file(lang_orphan, lang_orphan_file)
            else:
                lang_orphan_file.unlink(missing_ok=True)

            stats_u = len(lang_strings)
            stats_o = len(lang_orphan)
            stats_t = stats_u + stats_o
            echo(f"total {stats_t}, unique {stats_u}, orphan {stats_o}")


def compile_lang(chapter, lang):
    """Assemble json for continuous localization"""
    echo(f"assemble: ch{chapter} ({lang})")
    textdata = get_textdata(chapter)
    merged_dict = { "date": str(time.time_ns())[:-5] }
    in_dict = merge_json(textdata["jsons_fullpath"][BASE_LANG])
    out_dict = merge_json(textdata["jsons_fullpath"][lang])
    count_all = len(in_dict)
    count_translated = 0

    for k, v in out_dict.items():
        if v == None:
            out_dict[k] = in_dict[k]
            continue
        count_translated += 1

    merged_dict.update(out_dict)

    l10n_progress = str(round(((count_translated / count_all) * 100), 2)) + "%"
    echo(f"Translated {count_translated}/{count_all} ({l10n_progress})")

    try:
        out_dir = textdata["game_dir"] / f"chapter{chapter}_windows" / "lang"
    except KeyError:
        out_dir = textdata["pwd"]
    merged_file = out_dir / f"lang_{lang}.json"
    echo(str(merged_file))

    dict2file(merged_dict, merged_file)


def fetch_dump(files: list):
    """Update the text dump"""
    for filename in files:
        echo(f"fetch: {filename}")
        request = urllib.request.Request(f"{DUMP_URL}/{filename}")
        with open((PWD / "common" / filename), "w", encoding="utf-8") as f:
            f.write(urllib.request.urlopen(request, timeout=10).read().decode())


def init_lang(lang):
    """Populate new language with empty json files. This command can be used after first init"""
    for chapter in CHAPTERS:
        textdata = get_textdata(chapter)

        # check for files diff
        for j in textdata["jsons"][BASE_LANG]:
            if j not in textdata["jsons"][lang]:
                dict2file({}, (textdata["dir"][lang] / j))

        for j in textdata["jsons"][lang]:
            if j not in textdata["jsons"][BASE_LANG]:
                j.unlink(missing_ok=True)

        for j in textdata["jsons"][BASE_LANG]:
            in_json = textdata["dir"][BASE_LANG] / j
            out_json = textdata["dir"][lang] / j
            in_dict = file2dict(in_json)
            out_dict = file2dict(out_json)
            # fill with null
            for msgid in in_dict:
                if msgid not in out_dict:
                    out_dict[msgid] = None
            # re-sort keys
            out_dict = {k: out_dict[k] for k in in_dict}
            dict2file(out_dict, out_json)


def launch_game(chapter):
    textdata = get_textdata(chapter)
    if "game_dir" not in textdata:
        return
    subprocess.run(
        [
            (textdata["game_dir"] / "DELTARUNE.exe"),
            "-game", "data.win", "launcher", "switch_-1", "returning_0"
        ],
        cwd=(textdata["game_dir"] / f"chapter{chapter}_windows"),
        stdin=subprocess.DEVNULL
    )


subcmd = ""

for i, arg in enumerate(sys.argv):
    if i == 1: subcmd = arg
    if i == 2: L10N_CHAPTER = arg
    if i == 3: L10N_LANG = arg

match subcmd:
    case "c"|"compile":
        compile_lang(L10N_CHAPTER, L10N_LANG)
        launch_game(L10N_CHAPTER)
    case "i"|"init":
        init_lang(L10N_LANG)
    case "s"|"split":
        split_dump()
    case "u"|"update":
        fetch_dump(["lang.json", "sourcemap.json"])
        split_dump()
    case "l"|"launch":
        launch_game(L10N_CHAPTER)
    case _:
        helpmsg()
