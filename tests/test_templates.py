

def test_a_launch_does_not_claim_a_verdict_it_does_not_have():
    """ADR-073: the spawn is fire-and-forget, so "Opened Brave." was an
    assertion the executor cannot make. It says what it did instead."""
    from friday.errors import Outcome
    from friday.ui import templates

    assert templates.render(Outcome.OK, "Brave", detach=True) == "Launching Brave."


def test_a_command_speaks_what_it_did_not_that_it_opened_something():
    """The six G12 command tools shared the launch template, so "volume up"
    was spoken as "Opened volume up." — nonsense nobody heard, because the
    live G12 rows of docs/reality-check.md were never ticked."""
    from friday.errors import Outcome
    from friday.ui import templates

    assert templates.render(Outcome.OK, "volume up") == "Volume up."
    assert templates.render(Outcome.OK, "Wi-Fi off") == "Wi-Fi off."
