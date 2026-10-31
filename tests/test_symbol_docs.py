from pathlib import Path

from typokiller.symbol_docs import bash_files, doc_source, tldr_blocks


def write_files(folder: Path, files: dict[str, str]):
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text)


def test_a_tldr_page_is_its_cleaned_commands_one_to_a_line_under_the_page_name_without_the_descriptions():
    page = (
        "# tar\n\n> Archiving utility.\n\n"
        "- Create an archive:\n\n`tar cf {{path/to/target.tar}} {{path/to/file1 path/to/file2 ...}}`\n\n"
        "- Extract it:\n\n`tar xf {{path/to/source.tar}} {{[-C|--directory]}} {{path/to/directory}}`\n\n"
        "- Keep other brackets:\n\n`mv {{[-n|--no-clobber]}} [a-z]* {{[y|n]}}`\n"
    )

    assert tldr_blocks(Path("tldr/pages/common/tar.md"), page) == [
        ("tar", "tar cf target.tar file1 file2 ...\ntar xf source.tar -C directory\nmv -n [a-z]* [y|n]")
    ]


def test_the_bash_files_are_every_file_of_examples_but_those_in_loadables(tmp_path):
    write_files(
        tmp_path,
        {
            "INDEX.txt": "index",
            "scripts/a.sh": "a",
            "functions/deep/b": "b",
            "loadables/c.c": "c",
            "loadables/sub/d.c": "d",
            "loadables.txt": "not the folder",
        },
    )

    chosen = [path.relative_to(tmp_path).as_posix() for path in bash_files(tmp_path)]

    assert chosen == ["INDEX.txt", "functions/deep/b", "loadables.txt", "scripts/a.sh"]


def test_a_file_that_is_not_text_is_left_out_of_a_doc_source(tmp_path):
    write_files(tmp_path, {"a.txt": "echo $HOME > /dev/null\n"})
    (tmp_path / "image.png").write_bytes(b"\x89PNG\xff\xfe\x00")

    title, text, passages = doc_source(
        "Docs", tmp_path, sorted(tmp_path.iterdir()), lambda path, code: [(path.name, code)], 0.05, 5, 200
    )

    assert text == "--- a.txt\necho $HOME > /dev/null\n"
    assert passages == [("a.txt", "echo $HOME > /dev/null")]
