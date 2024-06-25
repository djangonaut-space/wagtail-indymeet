from __future__ import annotations

from wagtail import blocks
from wagtail.contrib.table_block.blocks import TableBlock
from wagtail.images.blocks import ImageChooserBlock

CODE_LANGUAGE_OPTIONS = (
    ("Python", "python"),
    ("Markup", "html"),
    ("CSS", "css"),
    ("Clojure", "clojure"),
    ("Bash", "shell"),
    ("Django", "django"),
    ("Jinja2", "jinja2"),
    ("Docker", "dockerfile"),
    ("Git", "git"),
    ("GraphQL", "graphql"),
    ("Handlebars", "handlebars"),
    (".ignore", "gitignore"),
    ("JSON", "json"),
    ("JSON5", "json5"),
    ("Markdown", "md"),
    ("Markdown", "md"),
    ("React JSX", "jsx"),
    ("React TSX", "tsx"),
    ("SASS", "sass"),
    ("SCSS", "scss"),
    ("TypeScript", "ts"),
    ("vim", "vim"),
)


class HeadingBlock(blocks.StructBlock):
    size = blocks.ChoiceBlock(
        choices=[
            ("text-5xl", "h1"),
            ("text-4xl", "h2"),
            ("text-3xl", "h3"),
            ("text-2xl", "h4"),
            ("text-xl", "h5"),
            ("text-lg", "h6"),
        ],
        icon="title",
    )
    heading = blocks.CharBlock(max_length=255, class_name="heading-blog")

    def __str__(self):
        return self.heading

    class Meta:
        template = "blocks/heading.html"


class ListItemBlock(blocks.StructBlock):
    text = blocks.CharBlock()
    link = blocks.URLBlock(required=False)
    icon = blocks.CharBlock(
        max_length=50,
        required=False,
        help_text="Use font awesome class names ex: 'fa-solid fa-xs fa-tv'",
    )
    icon_color = blocks.CharBlock(
        max_length=50, required=False, help_text="Names, hex etc ex: 'grey', '#999999'"
    )


class ListBlock(blocks.StructBlock):
    style = blocks.ChoiceBlock(
        choices=[
            ("circle", "unordered list"),
            ("decimal", "ordered list"),
            ("none", "unstyled"),
        ]
    )
    list_items = blocks.ListBlock(ListItemBlock())

    def __str__(self):
        return self.text

    class Meta:
        template = "blocks/list.html"


class TextWithHeadingBlock(blocks.StructBlock):
    heading = blocks.CharBlock(max_length=255, class_name="heading-blog")
    text = blocks.TextBlock()

    def __str__(self):
        return self.heading

    class Meta:
        label = "Text Block with Header"
        template = "blocks/text-with-heading.html"


class TextWithHeadingWithRightImageBlock(blocks.StructBlock):
    heading = blocks.CharBlock(
        max_length=255, class_name="heading-blog", required=False
    )
    text = blocks.TextBlock()
    image = ImageChooserBlock()

    def __str__(self):
        return self.heading

    class Meta:
        label = "Text Block with Header: Right Image"
        template = "blocks/text-with-heading-right-image.html"


class TextWithHeadingWithLeftImageBlock(blocks.StructBlock):
    heading = blocks.CharBlock(max_length=255, class_name="blog", required=False)
    text = blocks.TextBlock()
    image = ImageChooserBlock()

    def __str__(self):
        return self.heading

    class Meta:
        label = "Text Block with Header: Left Image"
        template = "blocks/text-with-heading-left-image.html"


class QuoteBlock(blocks.StructBlock):
    text = blocks.CharBlock(max_length=255)
    attribution = blocks.CharBlock(max_length=255)

    def __str__(self):
        return self.attribution

    class Meta:
        label = "Quote Block"
        template = "blocks/quote-block.html"


class QuoteLeftImageBlock(blocks.StructBlock):
    quote = blocks.TextBlock()
    byline = blocks.CharBlock(max_length=255)
    image = ImageChooserBlock()

    def __str__(self):
        return self.byline

    class Meta:
        template = "blocks/quote-left-image.html"
        label = "Person Quote and Image"
        form_classname = "Full"


class VideoEmbed(blocks.StructBlock):
    heading = blocks.CharBlock(max_length=255)
    text = blocks.TextBlock()
    # TODO: Add color and embed field

    def __str__(self):
        return self.heading

    class Meta:
        label = "Video Embed"
        template = "blocks/video-embed.html"


class CodeBlock(blocks.StructBlock):
    language = blocks.ChoiceBlock(choices=CODE_LANGUAGE_OPTIONS)
    caption = blocks.CharBlock(max_length=255, blank=True)
    page = blocks.CharBlock(max_length=255, blank=True)
    code = blocks.TextBlock(max_length=1000, blank=True)

    def __str__(self):
        return self.caption

    class Meta:
        label = "Code Block"
        template = "blocks/code-block.html"


class TextHeadingImageBlock(blocks.StructBlock):
    heading = blocks.CharBlock(max_length=255, required=False)
    text = blocks.TextBlock(required=False)
    image = ImageChooserBlock()

    def __str__(self):
        return self.heading

    class Meta:
        label = "Text, Header and Image"
        template = "blocks/text-image-heading.html"


class CustomTableBlock(TableBlock):
    class Meta:
        template = "blocks/table.html"


class CustomCaption(blocks.StructBlock):
    text = blocks.TextBlock()

    class Meta:
        template = "blocks/caption.html"


class VerticalImageCardBlock(blocks.StreamBlock):
    images = blocks.StructBlock(
        [
            ("image", ImageChooserBlock(required=True, help_text="size: 800X450px")),
            ("caption", CustomCaption()),
            (
                "description",
                blocks.CharBlock(
                    max_length=300, required=False, help_text="300 characters limit"
                ),
            ),
            ("link", blocks.URLBlock(required=False)),
        ]
    )

    class Meta:
        template = "blocks/vertical_image_cards_block.html"


class RichTextBlock(blocks.StructBlock):
    text = blocks.RichTextBlock(
        max_length=10000,
        features=[
            "embed",
            "bold",
            "italic",
            "link",
            "superscript",
            "subscript",
            "strikethrough",
            "code",
            "hr",
        ],
        label="Rich Text",
        icon="title",
    )

    class Meta:
        template = "blocks/rich_text.html"


class BaseStreamBlock(blocks.StreamBlock):
    heading = HeadingBlock(label="Heading", icon="h1")
    rich_text = RichTextBlock()
    list = ListBlock(label="List", icon="list-ol")
    paragraph = blocks.TextBlock(max_length=10000)
    html = blocks.RawHTMLBlock(icon="code", label="Raw HTML")
    image = ImageChooserBlock()
    caption = CustomCaption()
    text_with_heading = TextWithHeadingBlock()
    text_with_heading_and_image = TextHeadingImageBlock()
    text_with_heading_and_right_image = TextWithHeadingWithRightImageBlock()
    text_with_heading_and_left_image = TextWithHeadingWithLeftImageBlock()
    left_quote_right_image = QuoteLeftImageBlock(icon="openquote")
    video_embed = VideoEmbed()
    table = CustomTableBlock()
    code_block = CodeBlock()
    vertical_image_cards = VerticalImageCardBlock()
