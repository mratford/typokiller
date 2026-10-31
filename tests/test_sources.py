from typokiller.sources import code_passages, cut_code, cut_prose, lesson_passages, prose_passages


def test_prose_is_cut_at_sentence_ends_with_as_many_whole_sentences_as_fit():
    text = "First one is here. Second one is here. Third one is here. Fourth."

    assert cut_prose(text, 40, 5) == ["First one is here. Second one is here.", "Third one is here. Fourth."]


def test_prose_is_not_cut_after_an_abbreviation_such_as_mr():
    text = "Aaaa bbbb cccc. Said Mr. Webster went home."

    # The limit falls just after "Mr.", but the cut is at the sentence end before it.
    assert cut_prose(text, 30, 5) == ["Aaaa bbbb cccc.", "Said Mr. Webster went home."]


def test_prose_is_not_cut_between_initials():
    text = "Aaaa bbbb cccc. Then J. K. Rowling wrote."

    assert cut_prose(text, 25, 5) == ["Aaaa bbbb cccc.", "Then J. K. Rowling wrote."]


def test_a_word_that_only_ends_like_an_initial_is_a_sentence_end():
    text = "Aaaa bbbb NASA. Then go home now."

    assert cut_prose(text, 25, 5) == ["Aaaa bbbb NASA.", "Then go home now."]


def test_a_sentence_over_the_limit_is_cut_at_the_last_semicolon_colon_or_comma_that_fits_else_at_a_space():
    text = "alpha beta, gamma delta; epsilon zeta eta theta iota kappa"

    # The first cut is at the semicolon, not the comma before it. The rest has none, so it is cut at a space.
    assert cut_prose(text, 25, 5) == ["alpha beta, gamma delta;", "epsilon zeta eta theta", "iota kappa"]


def test_a_last_prose_piece_shorter_than_min_length_is_joined_to_the_piece_before_it():
    text = "Long sentence number one is here. Hi there."

    assert cut_prose(text, 35, 10) == [text]


def test_code_is_cut_at_the_last_blank_line_that_ends_a_piece_between_half_and_a_quarter_over_the_limit():
    code = "def a():\n    return 1\n\ndef b():\n    return 2\n\ndef c():\n    return 3"

    # The second blank line ends a piece of 44 characters: over 40, and under 50.
    pieces = cut_code(code, 40, 5)

    assert pieces == ["def a():\n    return 1\n\ndef b():\n    return 2", "def c():\n    return 3"]
    # A piece is not cut again, so a second cut of stored Passages does nothing.
    assert cut_code(pieces[0], 40, 5) == [pieces[0]]


def test_a_blank_line_before_half_the_limit_is_not_used_when_a_later_line_break_fits():
    code = "a = 1\n\nbbbbbbbbbb = 2\nccccccccccc = 3\ndddddddddd = 4\neeeeeeeeee = 5"

    assert cut_code(code, 40, 5) == ["a = 1\n\nbbbbbbbbbb = 2\nccccccccccc = 3", "dddddddddd = 4\neeeeeeeeee = 5"]


def test_a_single_code_line_over_the_limit_stays_whole():
    long = "x = '" + "a" * 50 + "'"

    assert cut_code(f"{long}\ny = 2", 20, 3) == [long, "y = 2"]


def test_a_last_code_piece_shorter_than_min_length_is_joined_to_the_piece_before_it():
    code = f"aaaaaaaaaaaaaa\n{'b' * 20}\nz = 1"

    # The rest, "bbb...\nz = 1", is 26 characters: over a quarter more than 20, so it is cut.
    assert cut_code(code, 20, 6) == ["aaaaaaaaaaaaaa", f"{'b' * 20}\nz = 1"]


def test_a_code_piece_does_not_end_with_a_blank_line():
    code = "aaaaaaa\n\n" + "b" * 26

    assert cut_code(code, 20, 5) == ["aaaaaaa", "b" * 26]


def test_a_long_function_in_a_code_file_is_cut_by_code_chars():
    code = "def f():\n    a = 1\n    b = 2\n    c = 3\n"

    assert code_passages(code, 0.05, 5, 20) == (["def f():\n    a = 1", "    b = 2\n    c = 3"], 0)


def test_min_length_and_max_dropped_are_checked_on_the_whole_paragraph_before_it_is_cut():
    paragraphs = ["Short one. Another sentence follows, and it is too long for one piece.", "Hi."]

    greek = "Ἐν ἀρχῇ ἦν ὁ λόγος. A clean sentence follows, and it is long enough."

    assert prose_passages([greek], 0.05, 20, 40) == ([], 1)  # too much dropped in all, though one piece is clean
    assert prose_passages(paragraphs, 0.05, 20, 40) == (
        # "Short one." is under min_length by itself, but its paragraph is long enough.
        ["Short one.", "Another sentence follows,", "and it is too long for one piece."],
        1,  # "Hi."
    )


def test_each_piece_of_a_lesson_paragraph_or_code_block_keeps_its_heading():
    markdown = (
        "# Title\n\n## Heading\n\n"
        "Short one. Another sentence follows, and it is too long for one piece.\n\n"
        "```python\naaaaaaaaaa = 1\n\nbbbbbbbbbb = 2\n\ncccccccccc = 3\n\ndddddddddd = 4\n```\n"
    )

    parts, skipped = lesson_passages(markdown, 0.05, 10, 40, 40)

    assert skipped == 0
    assert parts == [
        ("Heading", "Short one.", False),
        ("Heading", "Another sentence follows,", False),
        ("Heading", "and it is too long for one piece.", False),
        ("Heading", "aaaaaaaaaa = 1\n\nbbbbbbbbbb = 2\n\ncccccccccc = 3", True),
        ("Heading", "dddddddddd = 4", True),
    ]
