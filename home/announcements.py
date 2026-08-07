"""The weekly announcement copy organizers post to Discord each session.

This is the catalogue ``home.services.session_announcements`` copies into
``Announcement`` rows when a session's Discord is set up. The text is the
program's existing hand-written copy.

The parts that vary between sessions are handled two ways:

* Anything derivable from the session is a ``{format_field}`` filled in at
  generation time — see ``TEMPLATE_FIELDS`` for what's available.
* Anything that isn't (event links, speaker names, dates that depend on
  scheduling) stays a visible ``<placeholder>`` for an organizer to fill in
  while approving.

A template only sets ``needs_approval`` when a human genuinely has to touch
it. The weeks whose copy is complete once the session fields are filled in
post on their own, and carry no approval note.

The ``@Djangonauts``-style mentions below are role pings: at post time each
one that names a role on the Discord server is swapped for the ``<@&ROLE_ID>``
form Discord actually notifies on (see
``home.integrations.discord.service``). Names that don't match a role post
as plain text, so the role names here have to match the server's exactly.

One thing intentionally *not* in here: the guest-speaker announcement. It is
event-driven (sent the Friday before a talk), not anchored to a session week,
so organizers add it by hand.
"""

from dataclasses import dataclass

#: The ``{fields}`` a template message may use, filled in from the session by
#: ``home.services.session_announcements.build_template_context``.
TEMPLATE_FIELDS = ("organizers", "feedback_form_url", "session_name")


@dataclass(frozen=True)
class AnnouncementTemplate:
    """One week's announcement copy.

    Attributes:
        week_number: Session week the message belongs to. Week 1 is the
            official starting week, so week 0 posts the Monday before.
        message: The Discord message body, as a ``str.format`` template. The
            ``**Week N**`` header is added at post time by
            ``Announcement.discord_content``.
        needs_approval: Whether an organizer must review before it posts.
            False only when the rendered copy is complete as it stands.
        approval_note: What an organizer needs to change before approving.
            Empty when the announcement doesn't need approval.
    """

    week_number: int
    message: str
    needs_approval: bool = True
    approval_note: str = ""

    def render(self, context: dict[str, str]) -> str:
        """Fill the session-derived fields into the message copy."""
        return self.message.format(**context)


WEEK_0 = AnnouncementTemplate(
    week_number=0,
    message=(
        "Hello @Djangonauts, so lovely meeting you all! It's official — we've "
        "started!\n\n"
        "Your @Navigators should be scheduling your weekly catch-ups, your "
        "@Captains meet you bi-weekly and should be saying hello, and you "
        "should all have access to your personal workbooks! These have "
        "information on the program, and you can use them to keep notes and "
        "reflect on what you're doing.\n\n"
        "There is one more welcome session scheduled to meet each other "
        "later: <welcome event link>\n\n"
        "Use this week to get to know your team and think about what you want "
        "to work on. There are some suggestions in #ideas, but reach out to "
        "your Navigator (or each other!) if you're stuck.\n\n"
        "The organizers are {organizers} — we're here if you have any "
        "questions about the program. Don't hesitate to reach out with a "
        "question, concern or feedback!\n\n"
        "Talking of feedback, if you wish to give it anonymously, you can do "
        "so here: {feedback_form_url}\n\n"
        "Last but not least, please report any code of conduct issues to "
        "CoC@djangonaut.space — your experience here matters to us, let us "
        "help.\n"
        "https://github.com/djangonaut-space/program/blob/main/CODE_OF_CONDUCT.md"
    ),
    approval_note=(
        "Replace <welcome event link> with the remaining welcome session " "event link."
    ),
)

WEEK_1 = AnnouncementTemplate(
    week_number=1,
    message=(
        "Hello @Djangonauts, I hope you are all settling in well during this "
        "first official week of the program. I wanted to go over a couple of "
        "tips/tricks and reminders as you go through the program over the "
        "next 8 weeks.\n\n"
        "When you get a chance, spend some time exploring the different "
        "channels/discussions that are available: #general, #life, "
        "#show-and-tell, and more.\n\n"
        "We love seeing everyone sharing posts on LinkedIn and other socials "
        "about their onboarding calls and the start of the program. Please "
        "make sure you have permission from everyone before using their image "
        "(or repost something from the official Djangonaut Space page).\n\n"
        "We encourage everyone to check their workbooks on a weekly basis. "
        "There are a lot of helpful tips, articles, conference talks and more "
        "inside. These workbooks are a great way to track your progress "
        "during the program.\n\n"
        "If anyone has any questions or concerns please reach out to your "
        "@Navigators, @Captains or @Session Organizers. We are here to help "
        "any way we can."
    ),
    needs_approval=False,
)

WEEK_2 = AnnouncementTemplate(
    week_number=2,
    message=(
        "Hello @Djangonauts, we hope everyone is having a great start to Week "
        "2. Team meetings should be scheduled already with your Navigator and "
        "the rest of your team.\n\n"
        "If you still need help setting up your dev environment to start "
        "contributing, please reach out to your navigators this week to get "
        "things set up.\n\n"
        "Inside your workbooks you will find some learning material for this "
        "week, but here they are as well:\n"
        "- Writing Documentation — Django guide\n"
        "- Google's Technical Writing resource\n"
        "- Docs or it didn't happen! (45 minute talk)\n\n"
        "We will have a guest speaker next week (time TBD), so be on the "
        "lookout for that event here in Discord. We would love to see "
        "everyone there.\n\n"
        "As you start to make contributions and solve problems, please feel "
        "free to share them with the rest of the community in our #wins "
        "channel.\n\n"
        "We are so happy to have you all here. Good luck, have fun!"
    ),
    approval_note="Confirm a guest speaker is scheduled.",
)

WEEK_3 = AnnouncementTemplate(
    week_number=3,
    message=(
        "Hi @Djangonauts! I hope you all had a relaxing weekend — Week 3 is "
        "here, and we've got some exciting things happening across the "
        "galaxy.\n\n"
        "**Upcoming events**\n"
        "Here's what's on deck this week:\n"
        "- <date>: Co-writing session — perfect if you're starting to blog "
        "about your journey so far. Come write, share, and get inspired!\n"
        '- <date>: Talk by <speaker name> — "<talk title>"\n\n'
        "**Workbooks & collaboration**\n"
        "Inside your workbooks you'll find new resources to help guide your "
        "mission this week. Now that you've settled into your teams and the "
        "community, it's the perfect time to explore pair or mob programming "
        "opportunities. Working together is a great way to learn faster, "
        "share ideas and build stronger connections — there's no reason to "
        "fly solo when you can have a crew!\n\n"
        "**Celebrate your wins**\n"
        "As you collaborate and code this week, don't forget to share your "
        "achievements, big or small, in the #wins channel. Let's celebrate "
        "and hype each other up!\n\n"
        "**Need support?**\n"
        "If you have any questions or need help navigating your week, reach "
        "out to your @Navigators, @Captains or @Session Organizers — we're "
        "here to help you thrive."
    ),
    approval_note="Fill in the two event dates plus the speaker name and talk title.",
)

WEEK_4 = AnnouncementTemplate(
    week_number=4,
    message=(
        "Hi @Djangonauts, we are at the half way point of our journey. It "
        "seems like we just started!\n\n"
        "This is a great week for reflection. You have all been putting in a "
        "lot of effort this session — take some time to reflect on whether "
        "your current pace is sustainable. We want everyone to get the most "
        "out of this experience, but at the same time we do not want anyone "
        "getting burned out from the work. Open source is very much a "
        "marathon and not a race, so find a comfortable pace for you and keep "
        "going!\n\n"
        "There will be a half-way questionnaire sent out to everyone. Please "
        "find some time to fill it out this week.\n\n"
        "We strive to make the program better every session, and we cannot do "
        "that without honest feedback."
    ),
    needs_approval=False,
)

WEEK_5 = AnnouncementTemplate(
    week_number=5,
    message=(
        "Hello @Djangonauts, we are officially in Week 5! Now that we are in "
        "the second half of the program, we hope that everyone is feeling "
        "good and can see the light at the end of the tunnel.\n\n"
        "Anyone who missed <speaker name>'s talk can find the slides here: "
        "<slides link>. The recording of the talk can also be found here: "
        "<recording link>\n\n"
        "Please take some time to look through your Djangonaut workbooks this "
        "week and review the learning material, which includes links on "
        "testing, debugging and increasing your productivity.\n\n"
        "Thank you to everyone who was able to fill out the midway survey. We "
        "are taking time to review responses now.\n\n"
        "We have another exciting talk from <next speaker name> coming up for "
        "all of you on <date> (details are being finalized now). I will send "
        "out some additional messages to remind everyone in the next few "
        "days.\n\n"
        "As always, we are here to help. Please reach out if you need help "
        "with anything."
    ),
    approval_note=(
        "Fill in the first speaker's name, slides and recording links, plus "
        "the next speaker's name and date."
    ),
)

WEEK_6 = AnnouncementTemplate(
    week_number=6,
    message=(
        "Hi @Djangonauts, welcome to Week 6!\n\n"
        "We have a talk scheduled for you this week by <speaker name>: "
        '"<talk title>" — <Discord event link>\n\n'
        "We are nearing the end of the program, so look through your pending "
        "PRs and try to get comments addressed over these last couple of "
        "weeks if possible. We are proud of all the progress that everyone "
        "has made this session. Take some time this week to review all the "
        "great things you and your team have accomplished, and feel free to "
        "add any of these accomplishments to the #wins channel.\n\n"
        "When you get a chance, check out the workbooks this week. There is "
        "some cool learning material about databases and the ORM. This is a "
        "great way to learn more about it, especially if your PRs up to this "
        "point have been outside of the database/ORM realm.\n\n"
        "Have a great week — let's finish strong!"
    ),
    approval_note=(
        "Fill in the speaker name, talk title and Discord event link, or drop "
        "that paragraph if no talk is scheduled this week."
    ),
)

WEEK_7 = AnnouncementTemplate(
    week_number=7,
    message=(
        "Week 7 is here @Djangonauts! Time has gone by so quickly, but it has "
        "been so enjoyable watching everyone learn and grow inside of the "
        "Djangonaut community.\n\n"
        "This is the week of accessibility! We all have a unique perspective "
        "when it comes to accessing and interacting with technology. If you "
        "check your workbooks you will see some amazing links on "
        "accessibility in the Django ecosystem.\n\n"
        "If you missed the talk from <speaker name>, here are the recording "
        "and slides:\n"
        "- Watch the talk: <recording link>\n"
        "- Slides: <slides link>\n\n"
        "We are almost at the end of the session. Please take some time this "
        "week and next to think about where you would like to go after the "
        "session is over. There are so many wonderful things happening in the "
        "Django community and we would like this to be a launching pad into "
        "those."
    ),
    approval_note=(
        "Fill in the speaker name plus the recording and slides links, or "
        "drop that section if the talk hasn't happened."
    ),
)

WEEK_8 = AnnouncementTemplate(
    week_number=8,
    message=(
        "**{session_name}: Mission accomplished**\n\n"
        "Dear @Djangonauts, @Navigators and @Captains, as we wrap up this "
        "incredible session full of learning, contribution and "
        "collaboration, our hearts are full of gratitude. Thank you for "
        "dedicating your valuable time, energy and passion to making this "
        "program a success!\n\n"
        "Over the past 8 weeks we've navigated through galaxies of knowledge, "
        "tackled cosmic challenges and grown together as a crew. But this "
        "mission isn't just about this 8 week session — it's about the "
        "community you've become a part of, which will always be your orbit, "
        "ready to support you as you continue to explore the universe.\n\n"
        "**What's next?**\n"
        "To help us improve future sessions, we kindly request your anonymous "
        "feedback:\n"
        "- Djangonauts: <djangonaut survey link>\n"
        "- Officers: <officer survey link>\n\n"
        "Interested in leading the next adventure? Sign up to be a navigator, "
        "captain or session organizer for the next session: "
        "<interest form link>\n\n"
        "With respect to housekeeping, in the upcoming week you will see the "
        "following changes on our Discord server:\n"
        '- Current "Djangonaut" members will be assigned the role of '
        '"Star".\n'
        '- Team channels will be archived under "past-sessions". '
        "Communication remains unchanged, though channel names will differ "
        "slightly.\n\n"
        "Thank you for being part of this cosmic adventure. The stars are "
        "always here, and so are we.\n\n"
        "With love,\nDjangonaut Space Organizers"
    ),
    approval_note=(
        "Fill in the three links: Djangonaut survey, officer survey, and the "
        "interest form for next session's officers."
    ),
)

WEEKLY_ANNOUNCEMENTS: list[AnnouncementTemplate] = [
    WEEK_0,
    WEEK_1,
    WEEK_2,
    WEEK_3,
    WEEK_4,
    WEEK_5,
    WEEK_6,
    WEEK_7,
    WEEK_8,
]
