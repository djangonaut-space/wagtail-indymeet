from __future__ import annotations

from wagtail.blocks import RichTextBlock
from wagtail.blocks import StreamBlock
from wagtail.contrib.table_block.blocks import TableBlock
from wagtail.core import blocks
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
    heading = blocks.CharBlock(max_length=255, class_name="heading-blog")

    def __str__(self):
        return self.heading

    class Meta:
        template = "blocks/heading.html"


class TextWithHeadingBlock(blocks.StructBlock):
    heading = blocks.CharBlock(max_length=255, class_name="heading-blog")
    text = blocks.TextBlock()

    def __str__(self):
        return self.heading

    class Meta:
        label = "Text Block with Header"
        template = "blocks/text-with-heading.html"


class TextWithHeadingWithRightImageBlock(blocks.StructBlock):
    heading = blocks.CharBlock(max_length=255, class_name="heading-blog")
    text = blocks.TextBlock()
    image = ImageChooserBlock()

    def __str__(self):
        return self.heading

    class Meta:
        label = "Text Block with Header: Right Image"
        template = "blocks/text-with-heading-right-image.html"


class TextWithHeadingWithLeftImageBlock(blocks.StructBlock):
    heading = blocks.CharBlock(max_length=255, class_name="blog")
    text = blocks.TextBlock()
    image = ImageChooserBlock()

    def __str__(self):
        return self.heading

    class Meta:
        label = "Text Block with Header: Left Image"
        template = "blocks/text-with-heading-left-image.html"


class RightImageLeftTextBlock(blocks.StructBlock):
    image = ImageChooserBlock()
    text = blocks.TextBlock()

    def __str__(self):
        return self.text

    class Meta:
        label = "Text Block: Right Image"
        template = "blocks/right-image-left-text.html"


class LeftImageRightTextBlock(blocks.StructBlock):
    image = ImageChooserBlock()
    text = blocks.TextBlock()

    def __str__(self):
        return self.text

    class Meta:
        label = "Text Block: Left Image"
        template = "blocks/left-image-right-text.html"


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
    heading = blocks.CharBlock(max_length=255)
    text = blocks.TextBlock()
    image = ImageChooserBlock()
    # TODO: Add left or right side

    def __str__(self):
        return self.heading

    class Meta:
        label = "Text, Header and Image"
        template = "blocks/text-image-heading.html"


class BaseStreamBlock(StreamBlock):
    heading = HeadingBlock()
    paragraph = blocks.TextBlock()
    html = blocks.RawHTMLBlock(icon="code", label="Raw HTML")
    image = ImageChooserBlock()
    text_with_heading = TextWithHeadingBlock()
    text_with_heading_and_right_image = TextWithHeadingWithRightImageBlock()
    text_with_heading_and_left_image = TextWithHeadingWithLeftImageBlock()
    right_image_left_text = RightImageLeftTextBlock()
    left_image_right_text = LeftImageRightTextBlock()
    left_quote_right_image = QuoteLeftImageBlock()
    video_embed = VideoEmbed()
    table = TableBlock()
    code_block = CodeBlock()
    rich_text = RichTextBlock()
