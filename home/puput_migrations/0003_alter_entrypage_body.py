# Generated by Django 4.1.5 on 2023-12-27 17:52
import wagtail.blocks
import wagtail.contrib.table_block.blocks
import wagtail.fields
import wagtail.images.blocks
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("puput", "0002_entrypage_markdown_body"),
    ]

    operations = [
        migrations.AlterField(
            model_name="entrypage",
            name="body",
            field=wagtail.fields.StreamField(
                [
                    (
                        "heading",
                        wagtail.blocks.StructBlock(
                            [
                                (
                                    "heading",
                                    wagtail.blocks.CharBlock(
                                        class_name="heading-blog", max_length=255
                                    ),
                                )
                            ]
                        ),
                    ),
                    ("paragraph", wagtail.blocks.CharBlock(max_length=255)),
                    (
                        "html",
                        wagtail.blocks.RawHTMLBlock(icon="code", label="Raw HTML"),
                    ),
                    ("image", wagtail.images.blocks.ImageChooserBlock()),
                    (
                        "text_with_heading",
                        wagtail.blocks.StructBlock(
                            [
                                ("heading", wagtail.blocks.CharBlock(max_length=255)),
                                ("text", wagtail.blocks.TextBlock()),
                                ("image", wagtail.images.blocks.ImageChooserBlock()),
                            ]
                        ),
                    ),
                    (
                        "text_with_heading_and_right_image",
                        wagtail.blocks.StructBlock(
                            [
                                (
                                    "heading",
                                    wagtail.blocks.CharBlock(
                                        class_name="heading-blog", max_length=255
                                    ),
                                ),
                                ("text", wagtail.blocks.TextBlock()),
                                ("image", wagtail.images.blocks.ImageChooserBlock()),
                            ]
                        ),
                    ),
                    (
                        "text_with_heading_and_left_image",
                        wagtail.blocks.StructBlock(
                            [
                                (
                                    "heading",
                                    wagtail.blocks.CharBlock(
                                        class_name="blog", max_length=255
                                    ),
                                ),
                                ("text", wagtail.blocks.TextBlock()),
                                ("image", wagtail.images.blocks.ImageChooserBlock()),
                            ]
                        ),
                    ),
                    (
                        "right_image_left_text",
                        wagtail.blocks.StructBlock(
                            [
                                ("image", wagtail.images.blocks.ImageChooserBlock()),
                                ("text", wagtail.blocks.TextBlock()),
                            ]
                        ),
                    ),
                    (
                        "left_image_right_text",
                        wagtail.blocks.StructBlock(
                            [
                                ("image", wagtail.images.blocks.ImageChooserBlock()),
                                ("text", wagtail.blocks.TextBlock()),
                            ]
                        ),
                    ),
                    (
                        "left_quote_right_image",
                        wagtail.blocks.StructBlock(
                            [
                                ("quote", wagtail.blocks.TextBlock()),
                                ("byline", wagtail.blocks.CharBlock(max_length=255)),
                                ("image", wagtail.images.blocks.ImageChooserBlock()),
                            ]
                        ),
                    ),
                    (
                        "video_embed",
                        wagtail.blocks.StructBlock(
                            [
                                ("heading", wagtail.blocks.CharBlock(max_length=255)),
                                ("text", wagtail.blocks.TextBlock()),
                            ]
                        ),
                    ),
                    ("table", wagtail.contrib.table_block.blocks.TableBlock()),
                    (
                        "code_block",
                        wagtail.blocks.StructBlock(
                            [
                                (
                                    "language",
                                    wagtail.blocks.ChoiceBlock(
                                        choices=[
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
                                        ]
                                    ),
                                ),
                                (
                                    "caption",
                                    wagtail.blocks.CharBlock(
                                        blank=True, max_length=255
                                    ),
                                ),
                                (
                                    "page",
                                    wagtail.blocks.CharBlock(
                                        blank=True, max_length=255
                                    ),
                                ),
                                (
                                    "code",
                                    wagtail.blocks.TextBlock(
                                        blank=True, max_length=1000
                                    ),
                                ),
                            ]
                        ),
                    ),
                    ("rich_text", wagtail.blocks.RichTextBlock()),
                ],
                null=True,
                use_json_field=True,
                verbose_name="StreamField Body",
            ),
        ),
    ]
