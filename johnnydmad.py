import configparser
import os
import sys

from collections import Counter
from operator import itemgetter

sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__), "mfvitools"))

from musicrandomizer import *
from insertmfvi import byte_insert, int_insert
from mml2mfvi import mml_to_akao

## TO DO LIST (* = essentially complete)
# * finish ripping FF6 vanilla songs
# * opera mode - johnnydmad side
# * tierboss - coding
# - tierboss - mml setup
# * write metadata to spoiler
# - specify seed in jdm launcher
# - credits generator devtool
# * music frequency devtool
# * adjust frequency for battleprog to prevent skewing late
# * silent mode for insertmfvi
# * select alternate music.txt (curator mode)
# - external ignorelist for songs and/or sources
# * ensure function with pyinstaller
# - reconcile music player w/ Myria disable sound hack
# - integration with BC randomizer
# - opera mode - beyondchaos side
# - allow music sourced from ROM, if specified by host / integrate mfvi2mml
# - allow selection of less intrusive mode(s) in jdm launcher (no event edits, e.g.)
# - test with Gaiden
# - test with WC

def print_progress_bar(cur, max):
    pct = (cur / max) * 100
    cursor = " >)|(<-"
    full_boxes = int(pct // 2)
    cursor_idx = int((pct % 2) * (len(cursor)/2))
    boxtext = cursor[-1] * full_boxes + cursor[cursor_idx]
    print(f"\r[{boxtext:<50}] {cur}/{max}", end="", flush=True)
    
def johnnydmad():
    print("johnnydmad EX5 early test")
    
    print("using ff6_plus.smc as source")
    with open("ff6_plus.smc", "rb") as f:
        inrom = f.read()
        
    f_chaos = False
    kw = {}
    while True:
        print()
        if "playlist_filename" in kw:
            print(f"Playlist file is set to {kw['playlist_filename']}")
        print()
        print("press enter to continue or type:")
        print('    "chaos" to test chaotic mode')
        print('    "sfxv" to check songs for errors, sorted by longest sequence variant')
        print('    "mem" to check songs for errors, sorted by highest memory use variant')
        print('    "pool" to simulate many seeds and report the observed probability pools for each track')
        print('    "battle" to simulate many seeds and report probabilities for only battle music')
        print('    "pl FILENAME" to set FILENAME as playlist instead of default')
        i = input()
        print()
        if i.startswith("pl "):
            kw["playlist_filename"] = i[3:]
            continue
        break
    if i == "chaos":
        f_chaos = True
    if i == "sfxv":
        mass_test("sfx", **kw)
    elif i == "mem":
        mass_test("mem", **kw)
    elif i == "pool":
        pool_test(inrom, **kw)
    elif i == "battle":
        pool_test(inrom, battle_only=True, **kw)
    else:
        print('generating..')
        metadata = {}
        outrom = process_music(inrom, meta=metadata, f_chaos=f_chaos, **kw)
        outrom = process_formation_music_by_table(outrom)
        outrom = process_map_music(outrom)
        outrom = add_music_player(outrom, metadata)
    
        print("writing to mytest.smc")
        with open("mytest.smc", "wb") as f:
            f.write(outrom)
        
        get_music_spoiler()
        
#################################

def pool_test(inrom, battle_only=False, playlist_filename=None, **kwargs):
    results = {}
    iterations = 100
    
    print()
    for i in range(iterations):
        tracklist = process_music(inrom, pool_test=True, playlist_filename=playlist_filename)
        for track, song in tracklist.items():
            if track not in results:
                results[track] = []
            results[track].append(song)
        print_progress_bar(i, iterations)
    print()
    
    if battle_only:
        tracks_to_check = ["battle", "bat2", "bat3", "bat4", "mboss", "boss",
                           "atma", "dmad5", "tier1", "tier2", "tier3"]
    else:
        tracks_to_check = results.keys()
        
    for track in tracks_to_check:
        pool = results[track]
        if len(pool) < iterations:
            pool.extend(["not present"] * (iterations - len(pool)))
            
        print(f"[{track.upper()}]:")
        
        c = Counter(pool)
        rank = sorted(c.items(), key=itemgetter(1), reverse=True)
        songlen = max([len(s) for s in c.keys()])
        for song, reps in rank:
            pct = (reps / iterations) * 100
            print(f"    {pct:04.1f}% {song:<{songlen}} ({reps} / {iterations})")
        
def mass_test(sort, playlist_filename=None, **kwargs):
    global used_song_names
    testbed = [
        ("***", "plain", 0x4C, False),
        ("rain", "zozo", 0x29, True),
        ("wind", "ruin", 0x4F, True),
        ("train", "train", 0x20, False)
        ]
    #cursor = " >)|(<"
    playlist_map, _ = init_playlist(playlist_filename)
    results = []
    legacy_files = set()
    jukebox_titles = {}
    song_warnings = {}
    i = 0
    print("")
    for song in sorted(playlist_map):
        binsizes = {}
        memusage = 0
        debugtext = f"{song}: "
        song_warnings[song] = set()
        for type, trackname, idx, use_sfx in testbed:
            tl = Tracklist()
            tl.add_random(trackname, [song], idx=idx, allow_duplicates=True)
            variant = tl[trackname].variant
            if variant is None:
                variant = "_default_"
                
            mml = tl[trackname].mml
            if tl[trackname].is_legacy:
                legacy_files.add(song)
                iset = mml_to_akao(mml, variant=variant, inst_only=True)
                mml = append_legacy_imports(mml, iset, raw_inst=True)
            mml = apply_variant(mml, type, trackname, variant=variant)
            bin = mml_to_akao(mml, song + ' ' + trackname, sfxmode=use_sfx, variant=variant)[0]
            binsizes[type] = len(bin)
            
            if song not in jukebox_titles:
                jukebox_titles[song] = get_jukebox_title(mml, song)
            var_memusage = get_spc_memory_usage(mml, variant=variant, custompath=os.path.dirname(tl[trackname].file))
            debugtext += f"({var_memusage}) "
            memusage = max(memusage, var_memusage)
            
            if memusage > 3746:
                song_warnings[song].add("BRR memory overflow")
            if len(bin) > 0x1002:
                song_warnings[song].add("Sequence memory overflow")
            if "%f" not in mml:
                song_warnings[song].add("Echo FIR unset (%f)")
            if "%b" not in mml:
                song_warnings[song].add("Echo feedback unset (%b)")
            if "%v" not in mml:
                song_warnings[song].add("Echo volume unset (%v)")
        order = memusage if sort == "mem" else max(binsizes.values())
        results.append((order, song, binsizes, memusage))
        print_progress_bar(i, len(playlist_map))
        i += 1
        
    results = sorted(results)
    print("")
    for largest, song, binsizes, memusage in results:
        print(f"{song:<20} :: ", end="")
        for k, v in binsizes.items():
            print(f"[{k} ${v:0X}] ", end="")
        if song in legacy_files:
            print(f" :: ~{jukebox_titles[song]:<18}~", end="")
        else:
            print(f" :: <{jukebox_titles[song]:<18}>", end="")
        print(f" ({memusage})", end="")
        #if largest >= 0x1002 or memusage > 3746 or song in song_warnings:
        if song_warnings[song]:
            print(" ~~WARNING~~")
            for w in song_warnings[song]:
                print("    " + w)
        else:
            print("")
            

#################################
    
def add_music_player(rom, metadata):
    mp_data_chunk = b"\xA9\xAB\x9E\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x8E\xA6\x9E\xA7\xFE\x88\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x8E\xA6\x9E\xA7\xFE\x88\x88\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA8\xA9\x9E\xA7\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9A\xB0\x9A\xA4\x9E\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xB0\xA8\x9B\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAC\xA1\x9A\x9D\xA8\xB0\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAC\xAD\xAB\x9A\xA0\xA8\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA0\x9A\xAE\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9F\xA2\xA0\x9A\xAB\xA8\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9C\xA8\xA2\xA7\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9C\xB2\x9A\xA7\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA5\xA8\x9C\xA4\x9E\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAB\x9A\x9C\xA1\x9E\xA5\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAB\x9E\xA5\xA6\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAC\x9E\xAD\xB3\x9E\xAB\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9D\x9A\xAB\xB2\xA5\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9C\x9E\xA5\x9E\xAC\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9C\xA1\xA8\x9C\xA8\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9B\xA8\xAC\xAC\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9B\x9A\xAB\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA4\x9E\x9F\xA4\x9A\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA7\x9A\xAB\xAC\xA1\x9E\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9C\x9A\xAF\x9E\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAF\x9E\xA5\x9D\xAD\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA9\xAB\xA8\xAD\x9E\x9C\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9E\xA6\xA9\xA2\xAB\x9E\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAD\xAB\xA8\xA8\xA9\xAC\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9E\xAD\xA8\xB0\xA7\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x92\x85\x97\xC1\xFE\x96\x9A\xAD\x9E\xAB\x9F\x9A\xA5\xA5\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA1\xAE\xAB\xAB\xB2\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAD\xAB\x9A\xA2\xA7\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9E\xAC\xA9\x9E\xAB\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAE\xA5\xAD\xAB\xA8\xAC\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA4\xA8\xA5\xAD\xB3\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9B\x9A\xAD\xAD\xA5\x9E\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x94\xA7\xAE\xAC\x9E\x9D\xFE\x85\x9A\xA7\x9F\x9A\xAB\x9E\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x93\xA1\x9E\xFE\x96\x9E\x9D\x9D\xA2\xA7\xA0\xFE\x96\x9A\xA5\xAD\xB3\xFE\x88\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x80\xAB\xA2\x9A\xFE\x9D\xA2\xFE\x8C\x9E\xB3\xB3\xA8\xFE\x82\x9A\xAB\x9A\xAD\xAD\x9E\xAB\x9E\xFE\xFE\xFE\x00\xAD\xAB\x9E\xA7\x9C\xA1\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xB3\xA8\xB3\xA8\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAD\xA8\xB0\xA7\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xB0\xA1\x9A\xAD\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x92\x85\x97\xC1\xFE\x82\xAB\xA8\xB0\x9D\xFE\x8D\xA8\xA2\xAC\x9E\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA0\xA8\xA0\xA8\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9B\x9A\xA7\xA8\xA7\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAF\xA2\x9C\xAD\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAE\xA6\x9A\xAB\xA8\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA6\xA8\xA0\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9D\x9A\xA7\xA0\x9E\xAB\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9B\xA8\xAC\xAC\xB6\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAB\xAD\xA8\xB0\xA7\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9F\xA5\xA2\xA0\xA1\xAD\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9D\xA8\xA8\xA6\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA8\xB0\xB3\x9E\xAB\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAC\xA5\x9E\x9E\xA9\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x92\x85\x97\xC1\xFE\x96\xA2\xA7\x9D\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x92\x85\x97\xC1\xFE\x96\x9A\xAF\x9E\xAC\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9D\xA6\x9A\x9D\xB5\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x92\x85\x97\xC1\xFE\x93\xAB\x9A\xA2\xA7\xFE\x92\xAD\xA8\xA9\xA9\xA2\xA7\xA0\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAB\x9A\xA0\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAB\xA2\xA9\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x92\x85\x97\xC1\xFE\x82\xA1\xA8\x9C\xA8\x9B\xA8\xAC\xFE\x91\xAE\xA7\xA7\xA2\xA7\xA0\xFE\xFE\xFE\xFE\xFE\x00\x92\x85\x97\xC1\xFE\x96\x9A\xAD\x9E\xAB\x9F\x9A\xA5\xA5\xFE\xB6\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x8E\xAF\x9E\xAB\xAD\xAE\xAB\x9E\xFE\x88\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x8E\xAF\x9E\xAB\xAD\xAE\xAB\x9E\xFE\x88\x88\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x8E\xAF\x9E\xAB\xAD\xAE\xAB\x9E\xFE\x88\x88\x88\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x93\xA1\x9E\xFE\x96\x9E\x9D\x9D\xA2\xA7\xA0\xFE\x96\x9A\xA5\xAD\xB3\xFE\x88\x88\xFE\xFE\xFE\xFE\xFE\xFE\x00\x93\xA1\x9E\xFE\x96\x9E\x9D\x9D\xA2\xA7\xA0\xFE\x96\x9A\xA5\xAD\xB3\xFE\x88\x88\x88\xFE\xFE\xFE\xFE\xFE\x00\x93\xA1\x9E\xFE\x96\x9E\x9D\x9D\xA2\xA7\xA0\xFE\x96\x9A\xA5\xAD\xB3\xFE\x88\x95\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA6\xAD\x9E\xA4\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x92\x85\x97\xC1\xFE\x8D\x9E\xB0\xFE\x82\xA8\xA7\xAD\xA2\xA7\x9E\xA7\xAD\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x92\x85\x97\xC1\xFE\x82\xAB\x9A\xA7\x9E\xFE\x80\x9C\xAD\xA2\xAF\x9A\xAD\xA2\xA8\xA7\xFE\xFE\xFE\xFE\xFE\x00\x92\x85\x97\xC1\xFE\x85\xA2\xAB\x9E\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9F\x9C\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9F\x9A\xA5\x9C\xA8\xA7\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9C\xAE\xA5\xAD\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA4\xAD\xA8\xB0\x9E\xAB\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xB0\xA8\xAB\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9F\xA2\xA7\x9A\xA5\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9F\xA8\xAB\x9E\xAC\xAD\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x83\x9A\xA7\x9C\xA2\xA7\xA0\xFE\x8C\x9A\x9D\xFE\x88\x88\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x81\x9A\xA5\x9A\xA7\x9C\x9E\xFE\x88\xAC\xFE\x91\x9E\xAC\xAD\xA8\xAB\x9E\x9D\xFE\x88\xFE\xFE\xFE\xFE\xFE\x00\x81\x9A\xA5\x9A\xA7\x9C\x9E\xFE\x88\xAC\xFE\x91\x9E\xAC\xAD\xA8\xAB\x9E\x9D\xFE\x88\x88\xFE\xFE\xFE\xFE\x00\xAD\xA8\xA6\x9B\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9D\xAB\x9E\x9A\xA6\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA8\x9D\xA2\xA7\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9F\x9E\xA7\xA2\xB1\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA0\x9A\xAD\x9E\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA6\xAD\xB3\xA8\xB3\xA8\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9E\xA7\xA0\xA2\xA7\x9E\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xAD\xA8\xB0\xA7\xB6\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA2\xA7\xAD\xAB\xA8\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9B\x9A\xAD\xB6\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9B\x9A\xAD\xB7\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x9B\x9A\xAD\xB8\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\xA6\x9B\xA8\xAC\xAC\xC1\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\xFE\x00\x00\x60\x1B\x60\x36\x60\x51\x60\x6C\x60\x87\x60\xA2\x60\xBD\x60\xD8\x60\xF3\x60\x0E\x61\x29\x61\x44\x61\x5F\x61\x7A\x61\x95\x61\xB0\x61\xCB\x61\xE6\x61\x01\x62\x1C\x62\x37\x62\x52\x62\x6D\x62\x88\x62\xA3\x62\xBE\x62\xD9\x62\xF4\x62\x0F\x63\x2A\x63\x45\x63\x60\x63\x7B\x63\x96\x63\xB1\x63\xCC\x63\xE7\x63\x02\x64\x1D\x64\x38\x64\x53\x64\x6E\x64\x89\x64\xA4\x64\xBF\x64\xDA\x64\xF5\x64\x10\x65\x2B\x65\x46\x65\x61\x65\x7C\x65\x97\x65\xB2\x65\xCD\x65\xE8\x65\x03\x66\x1E\x66\x39\x66\x54\x66\x6F\x66\x8A\x66\xA5\x66\xC0\x66\xDB\x66\xF6\x66\x11\x67\x2C\x67\x47\x67\x62\x67\x7D\x67\x98\x67\xB3\x67\xCE\x67\xE9\x67\x04\x68\x1F\x68\x3A\x68\x55\x68\x70\x68\x8B\x68\xA6\x68\xC1\x68\xDC\x68\xF7\x68\x12\x69\x2D\x69\x48\x69\x63\x69\x7E\x69\x99\x69\xB4\x69\xCF\x69\xEA\x69\x05\x6A\x20\x6A\x01\x04\x5D\x21\x05\x17\x1B\x0D\x0A\x0B\x16\x18\x06\x2A\x07\x13\x5C\x23\x32\x2E\x2B\x1C\x0C\x51\x20\x09\x19\x28\x1D\x1A\x0E\x29\x3D\x10\x35\x15\x47\x59\x1F\x31\x12\x08\x0F\x4B\x36\x4F\x34\x5B\x55\x11\x4C\x5A\x37\x30\x2D\x56\x57\x58\x4D\x4E\x24\x5E\x5F\x60\x61\x14\x22\x33\x3B\x50\x2F\x38\x3E\x02\x03\x41\x42\x43\x27\x26\x44\x45\x46\x52\x53\x54\x25\x1E\x2C\x39\x3A\x3C\x3F\x40\x48\x49\x4A\x00"
    mp_program_chunk = b"\xAF\x12\xAF\x21\xAF\x30\xAF\x3F\xAF\x4E\xAF\x5D\xAF\x6C\xAF\x7B\x86\x2E\x90\x2E\x90\x2E\x90\x2E\x90\x2E\x7A\x2E\x60\xFA\xAA\x2E\x0F\x00\x00\x0F\x03\x00\x0F\x04\x00\x0F\x05\x00\x0F\x06\x00\x0F\x07\x00\x0F\x08\x00\x0F\x09\x00\x0F\x0A\x00\x07\x08\x00\x07\x08\x00\x18\x00\x00\x00\x9D\x39\x8B\x95\x00\x39\x7C\x8C\xAE\xAC\xA2\x9C\x00\xA0\xFD\x37\x20\xF9\x02\xA9\x20\x85\x29\xA0\x4A\xFA\x60\x20\xB2\x0E\xA9\x7B\x85\x27\x64\x26\x60\x20\xB2\x0E\xA9\x04\x85\x27\x64\x26\x60\xA9\x04\x85\x26\xAD\x80\x1F\x85\xD2\xAD\x02\x13\x85\xD3\x60\xA5\xD2\x8D\x01\x13\xA9\x10\x8D\x00\x13\xA5\xD3\x8D\x02\x13\x22\x04\x00\xC5\xA9\xFF\x85\x27\x60\x20\x2F\x35\x20\x04\x69\xA9\x01\x8D\x07\x21\xA9\x02\x85\x46\x64\x4A\x64\x49\xA9\xFF\x85\x5F\x20\xF6\xFA\x20\xFF\xFA\x20\xB0\x07\x20\xBB\xFB\x20\x0A\xFC\xEA\xEA\xEA\x20\x7E\xFB\xA9\x7C\x85\x27\xA9\x01\x85\x26\x4C\x41\x35\x20\xFD\x0E\x20\xE3\xFC\x20\xFC\xFA\xA5\x08\x89\x80\xF0\x0B\x7B\xA5\x4B\xAA\xBF\x89\x9D\x7E\x4C\x13\xFD\xA5\x09\x89\x80\xF0\x03\x20\x6A\xFA\x60\xA0\x05\xFB\x4C\xFE\x05\x20\x5F\xFC\xA0\x0A\xFB\x4C\x48\x06\x01\x00\x00\x01\x0D\x08\x34\x08\x40\x08\x4C\x08\x58\x08\x64\x08\x70\x08\x7C\x08\x88\x08\x94\x08\xA0\x08\xAC\x08\xB8\x08\xC4\x00\x15\x79\x81\x84\x98\x8E\x8D\x83\xFE\x82\x87\x80\x8E\x92\xFE\x89\x94\x8A\x84\x81\x8E\x97\x27\x00\x00\x08\x00\x00\x0C\xD4\xFF\x0C\xD8\xFF\x0C\xDC\xFF\x0C\xE0\xFF\x0C\xE4\xFF\x0C\xE8\xFF\x0C\xEC\xFF\x0C\xF0\xFF\x0C\xF4\xFF\x0C\xF8\xFF\x0C\xFC\xFF\x0C\x00\x00\x0C\x04\x00\x00\x2F\x00\x01\x50\x00\x00\x50\x00\x00\x10\x00\x01\x00\x8B\x58\x1C\x02\x8B\x59\x1C\x14\xA9\x02\x8D\x50\x43\xA9\x0D\x8D\x51\x43\xA0\x69\xFB\x8C\x52\x43\xA9\xC3\x8D\x54\x43\xA9\xC3\x8D\x57\x43\xA9\x20\x04\x43\xA9\x02\x8D\x60\x43\xA9\x0E\x8D\x61\x43\xA0\x3B\xFB\x8C\x62\x43\xA9\xC3\x8D\x64\x43\xA9\xC3\x8D\x67\x43\xA9\x40\x04\x43\x60\xA0\x76\xFB\x20\x41\x03\xA0\x7A\xFB\x20\x41\x03\x20\x52\x0E\x20\x15\x6A\x20\x19\x6A\x20\x3C\x6A\xA9\x2C\x85\x29\xA0\x25\xFB\x20\xF9\x02\xA9\x20\x85\x29\xA6\x00\xBF\xFD\x6A\xF0\xF0\x07\x9F\x89\x9D\x7E\xE8\x80\xF3\x8A\x38\xE9\x0D\xB0\x01\x7B\x85\x5C\xA9\x0D\x85\x5A\xA9\x01\x85\x5B\x20\x30\xFC\x20\x28\x0E\x4C\x6E\x0E\x20\x1F\x09\xA0\x00\x90\x8C\x04\x42\xA5\x5C\x8D\x06\x42\xEA\xEA\xEA\xEA\xEA\xC2\x20\xAD\x14\x42\x9F\x4A\x35\x7E\xA9\x2E\x00\x9F\xCA\x34\x7E\xE2\x20\x60\x20\x15\x6A\x20\xF7\x83\xA0\x0D\x00\x5A\x7B\xA5\xE5\xAA\xBF\x89\x9D\x7E\x48\xA2\x03\x00\xA5\xE6\x20\x9F\x80\x7B\x68\x20\x2E\xFD\xE6\xE5\xA5\xE6\x1A\x1A\x29\x1F\x85\xE6\x7A\x88\xD0\xDB\x60\xA5\x0B\x89\x0A\xF0\x13\xA5\x4E\xD0\x0A\xA5\x4A\xF0\x26\xC6\x50\xC6\x4A\x80\x62\xC6\x50\xC6\x4E\x60\x89\x05\xF0\x18\xA5\x54\x3A\xC5\x4E\xD0\x0C\xA5\x4A\xC5\x5C\xF0\x0A\xE6\x50\xE6\x4A\x80\x46\xE6\x50\xE6\x4E\x60\xA5\x0A\x89\x30\xF0\xF9\x89\x20\xF0\x1A\xA5\x4A\xC5\x5A\x90\x02\xA5\x5A\x85\xE0\xA5\x4A\x38\xE5\xE0\x85\x4A\xA5\x50\x38\xE5\xE0\x85\x50\x80\x1D\xA5\x5C\x38\xE5\x4A\xF0\x19\xC5\x5A\x90\x02\xA5\x5A\x85\xE0\xA5\x4A\x18\x65\xE0\x85\x4A\xA5\x50\x18\x65\xE0\x85\x50\x4C\x30\xFC\xA5\x54\x3A\x85\x4E\x18\x65\x4A\x85\x50\x60\xAD\x05\x13\xC9\x20\xD0\x05\xA5\x5F\xF0\x19\x60\xC9\x3B\xD0\x13\xA5\x5F\xF0\x08\x3A\xD0\x0C\xA0\xD0\x41\x80\x03\xA0\x40\x19\xC4\xCF\x90\x01\x60\xA9\x89\x8D\x00\x13\x22\x04\x00\xC5\xE6\x5F\x60\x8D\x01\x13\xA9\x10\x8D\x00\x13\xA9\xFF\x8D\x02\x13\x9C\x05\x13\x22\x04\x00\xC5\xA4\x00\x84\xCF\x64\x5F\x60\xA0\x8B\x9E\x8C\x81\x21\xC2\x21\x48\x8A\x69\x40\x00\x8F\x89\x9E\x7E\x68\x3A\x0A\xAA\xBF\x3B\x6A\xF0\xAA\xE2\x20\xCA\xE8\xBF\x00\x00\xF0\x8D\x80\x21\xD0\xF6\xA0\x89\x9E\x84\xE7\xA9\x7E\x85\xE9\x4C\xFF\x02"
    rom = byte_insert(rom, 0x3011A, b"\x20\x74\xFA\x4C\xBA\x01")
    rom = byte_insert(rom, 0x302D1, b"\x9B\xFA\xD2\xFA")
    rom = byte_insert(rom, 0x31DCB, b"\x20\x83\xFA\x64\x26\x60")
    rom = byte_insert(rom, 0x32E6A, b"\x10\xFA")
    rom = byte_insert(rom, 0x32F66, b"\x00\xFA")
    rom = byte_insert(rom, 0x32F77, b"\x00\xFA")
    rom = byte_insert(rom, 0x32F89, b"\x08")
    rom = byte_insert(rom, 0x33175, b"\x80\x04")
    rom = byte_insert(rom, 0x331BE, b"\x0F\x00\x00\x00\x00\x35\x5D\x07\x06")
    rom = byte_insert(rom, 0x3321A, b"\x20\x52\xFA")
    rom = byte_insert(rom, 0x33253, b"\x37\x7E")
    rom = byte_insert(rom, 0x332A0, b"\xBB\x7D")
    rom = byte_insert(rom, 0x332AC, b"\xC1")
    rom = byte_insert(rom, 0x336AE, b"\x20\xFA")
    rom = byte_insert(rom, 0x33741, b"\x45\xFA")
    rom = byte_insert(rom, 0x3376F, b"\x4A\xFA")
    rom = byte_insert(rom, 0x337FD, b"\xB9")
    rom = byte_insert(rom, 0x33804, b"\x77\x7D")
    rom = byte_insert(rom, 0x3380B, b"\xBF\x7D\xC1\x00\xF7")
    rom = byte_insert(rom, 0x3FA00, mp_program_chunk)
    rom = byte_insert(rom, 0x50627, b"\x12\xA5\x05\xF0\x12\xA2\xFF\xFF\xE8\xBF\xF9\x06\xC5\x30\x08\xC5\x01\xD0\xF5\xA9\x04\x04")
    rom = byte_insert(rom, 0x306000, mp_data_chunk)
    
    for id, name in metadata.items():
        b = bytearray()
        for c in name:
            if c in menu_text_table:
                b += menu_text_table[c]
            else:
                b += b"\xCF"
        b = b[:18]
        loc = 0x306000 + (id - 1) *0x1B + 8
        rom = byte_insert(rom, loc, b)
        
    return rom

menu_text_table = {
    'A': b'\x80',
    'B': b'\x81',
    'C': b'\x82',
    'D': b'\x83',
    'E': b'\x84',
    'F': b'\x85',
    'G': b'\x86',
    'H': b'\x87',
    'I': b'\x88',
    'J': b'\x89',
    'K': b'\x8A',
    'L': b'\x8B',
    'M': b'\x8C',
    'N': b'\x8D',
    'O': b'\x8E',
    'P': b'\x8F',
    'Q': b'\x90',
    'R': b'\x91',
    'S': b'\x92',
    'T': b'\x93',
    'U': b'\x94',
    'V': b'\x95',
    'W': b'\x96',
    'X': b'\x97',
    'Y': b'\x98',
    'Z': b'\x99',
    'a': b'\x9A',
    'b': b'\x9B',
    'c': b'\x9C',
    'd': b'\x9D',
    'e': b'\x9E',
    'f': b'\x9F',
    'g': b'\xA0',
    'h': b'\xA1',
    'i': b'\xA2',
    'j': b'\xA3',
    'k': b'\xA4',
    'l': b'\xA5',
    'm': b'\xA6',
    'n': b'\xA7',
    'o': b'\xA8',
    'p': b'\xA9',
    'q': b'\xAA',
    'r': b'\xAB',
    's': b'\xAC',
    't': b'\xAD',
    'u': b'\xAE',
    'v': b'\xAF',
    'w': b'\xB0',
    'x': b'\xB1',
    'y': b'\xB2',
    'z': b'\xB3',
    '0': b'\xB4',
    '1': b'\xB5',
    '2': b'\xB6',
    '3': b'\xB7',
    '4': b'\xB8',
    '5': b'\xB9',
    '6': b'\xBA',
    '7': b'\xBB',
    '8': b'\xBC',
    '9': b'\xBD',
    '!': b'\xBE',
    '?': b'\xBF',
    '/': b'\xC0',
    ':': b'\xC1',
    '"': b'\xC2',
    "'": b'\xC3',
    '-': b'\xC4',
    '.': b'\xC5',
    ',': b'\xC6',
    '_': b'\xC7', # ellipsis
    ';': b'\xC8',
    '#': b'\xC9',
    '+': b'\xCA',
    '(': b'\xCB',
    ')': b'\xCC',
    '%': b'\xCD',
    '~': b'\xCE', # tilde
    '*': b'\xCF', # asterisk
    '=': b'\xD2',
#   '„': b'\xD3', # (0132) two dot ellipsis
    '^': b'\xD4', # up arrow
    '>': b'\xD5', # right arrow
    '<': b'\xD6', # down left arrow                           
    '&': b'\xD7', # weird x
    '`': b'\xD8', # dagger
#   'Š': b'\xD9', # (0138) sword
    '|': b'\xDA', # spear
    '\\': b'\xDB', # katana
#   'ƒ': b'\xDC', # (0131) staff
#   '‹': b'\xDD', # (0139) brush
    '}': b'\xDE', # shuriken
    '@': b'\xDF', # flail
    '$': b'\xE0', # gambler
#   '€': b'\xE1', # (0128) claw
#   '†': b'\xE2', # (0134) shield
#   'Œ': b'\xE3', # (0140) helmet
#   '‡': b'\xE4', # (0135) armor 
#   '™': b'\xE5', # (0153) tools
#   '‰': b'\xE6', # (0137) scroll
    '{': b'\xE7', # ring
    '[': b'\xE8', # white magic
    ']': b'\xE9', # black magic
#   '•': b'\xEA', # (0149) gray magic
    ' ': b'\xFE'
    }

#################################

if __name__ == "__main__":
    johnnydmad()
    print("end")
    input()