<a name="readme-top"></a>
<!--
*** build from Best-README-Template.
-->



<!-- PROJECT SHIELDS -->
[![Run tests](https://github.com/djangonaut-space/wagtail-indymeet/actions/workflows/tests.yml/badge.svg)](https://github.com/djangonaut-space/wagtail-indymeet/actions/workflows/tests.yml)
<!-- [![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![MIT License][license-shield]][license-url] -->



<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://github.com/djangonaut-space/wagtail-indymeet/">
    <img src="indymeet/static/img/main-white-purple-background.png" alt="Djangonaut Space logo" height="80">
  </a>

  <h3 align="center">Djangonaut Space Website</h3>

  <p align="center">
    A Wagtail CMS clone of <a href="https://contributing.today">contributing today »</a>
    <br />
    <br />
    <a href="https://djangonaut.space">Visit site</a>
    ·
    <a href="https://github.com/djangonaut-space/wagtail-indymeet/issues/new">Report Bug</a>
    ·
    <a href="https://github.com/djangonaut-space/wagtail-indymeet/issues/new">Request Feature</a>
  </p>
</div>



<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li>
      <a href="#contributing">Contributing</a>
      <ul>
        <li><a href="#merging-changes">Merging Changes</a></li>
        <li><a href="#deployments">Deployments</a></li>
        <li><a href="#updating-dependencies">Updating Dependencies</a></li>
      </ul>
    </li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>



<!-- ABOUT THE PROJECT -->
## About The Project

We want to run a light weight virtual meetup/video series.

Here's why:
* Sometimes you want to connect with a community in real time.
* The culture of Twitch first streaming alienates as many audiences as it invites.
* Having a list of events easily shown as well as resources about speakers in the series.

We thought contributing.today did it well, but it's build on ASP.NET so we're building it in Python!

<p align="right">(<a href="#readme-top">back to top</a>)</p>



### Built With

This section should list any major frameworks/libraries used to bootstrap your project. Leave any add-ons/plugins for the acknowledgements section. Here are a few examples.

* [![Wagtail][Wagtail]][wagtail.org]
* [![Tailwind][tailwindcss.com]][tailwindcss.com]
* [![Alpine.Js][alpinejs.dev]][alpinejs.dev]
* [![Django][Djangoproject.com]][Djangoproject.com]

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- GETTING STARTED -->
## Getting Started


### Prerequisites

This is an example of how to list things you need to use the software and how to install them.
* Python version 3.11

### Installation

1. Clone the repo
   ```sh
   git clone https://github.com/dawnwages/wagtail-indymeet.git
   ```
2. create your virtual environment
   ```sh
   python -m venv venv
   ```
   activate in Linux:
   ```sh
   source venv/bin/activate
   ```
   activate in Windows:
   ```sh
   venv\Scripts\activate
   ```
3. Create a posgresql database
   ```sh
   psql -U postgres
   ```
   ```sh
   postgres=# CREATE DATABASE "djangonaut-space";
   postgres=# CREATE USER djangonaut WITH SUPERUSER PASSWORD 'djangonaut';
   postgres=# GRANT ALL PRIVILEGES ON DATABASE "djangonaut-space" TO djangonaut;
   ```
   ```sh
   postgres=# exit
   ```
4. install requirements:
   ```sh
   pip install -r requirements/requirements-dev.txt
   ```
   set up the git hook scripts
   ```sh
   pre-commit install
   ```
5. Copy `.env.template.local` file, rename to `.env` and use variables for your local postgres database.
   Copy in Linux:
   ```sh
   cp .env.template.local .env
   ```
   activate in Windows:
   ```sh
   copy .env.template.local .env
   ```
6. Run migrations and create superuser
   ```sh
   python manage.py migrate
   # Potentially load data first
   # python manage.py loaddata fixtures/data.json
   python manage.py createsuperuser
   ```
7. Install tailwind. You also need npm installed.
   ```sh
   python manage.py tailwind install
   ```
8. Run server locally
   ```sh
   python manage.py runserver
   ```
9. Run tailwind in another terminal locally
   ```sh
   python manage.py tailwind start
   ```

Alternatively, if you're not using Windows you can run the following instead of steps 8 and 9:

```shell
./scripts/local.sh
```

This will run both the Django server and the Tailwind watcher in the same terminal.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

#### Docker

If you have docker installed, alternatively

1. Have docker running and then run:
   ```sh
   docker-compose up
   ```

2. In a new terminal, run any setup commands you need such as
   ```sh
   docker-compose exec web python manage.py createsuperuser
   ```

3. Go to: http://127.0.0.1:8000/ and enjoy!


You will also want to createsuperuser, load/create data in order to use the blog, etc.

### Creating fixtures for local testing

**Backing up**
To create a fixture to share content with another person you should do the following:

```shell
python manage.py dumpdata --natural-foreign --indent 2 \
   -e contenttypes -e auth.permission \
   -e wagtailcore.groupcollectionpermission \
   -e wagtailcore.grouppagepermission \
   -e wagtailimages.rendition \
   -e sessions \
   -e admin \
   -e wagtailsearch.indexentry \
   -e accounts.userprofile \
   -o fixtures/data.json
```
Then make an archive/zip of your `media/` and `fixtures/` directories. This is because
the image files need to be copied alongside the data. If needed, you may want to delete
some images first before sharing.

**Restoring**

1. Make a backup of your current media directory. This is so you can revert later
on.
2. Unpack the archived file, and place the `media/` and `fixtures/` directories at the
top level of the project.
3. Create a new database such as ``createdb -U djangonaut -W -O djangonaut djangonaut-space2``
4. Change your settings or environment variables to point to the new database
5. ``python manage.py migrate``
6. ``python manage.py loaddata fixtures/data.json``


<!-- CONTRIBUTING -->
## Contributing

Contributions are what make the open source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

If you have a suggestion that would make this better, please fork the repo and create a pull request. You can also simply open an issue with the tag "enhancement".
Don't forget to give the project a star! Thanks again!

1. Fork the Project
2. [Install pre-commit](https://pre-commit.com/#install) `pre-commit install`
3. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
4. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
5. Push to the Branch (`git push origin feature/AmazingFeature`)
6. Open a Pull Request


### Testing

Tests can be written using [Django's TestCase syntax](https://docs.djangoproject.com/en/5.0/topics/testing/overview/)
or using [`pytest`](https://docs.pytest.org/).

To run the tests:

```shell
pytest
```

There are also Playwright tests that can be run. To run these tests:

```shell
# Be sure playwright is properly installed and has a test user for accessing /admin
playwright install --with-deps
# This is the actual test command
pytest -m playwright
# Run the tests in headed mode (so you can see the browser)
pytest -m playwright --headed
```

### Merging changes
Before merging your changes from your branch you should rebase on the latest version
of `develop`. For example:

```shell
# Switch to develop and pull latest
git switch develop
git pull origin develop

# Rebase your feature branch on develop
git switch feature/AmazingFeature
git rebase develop
# Force push since the commit history will have changed
git push origin feature/AmazingFeature -f

#
# Wait for CI tests to pass!
#

# Merge to develop and push to GitHub
git switch develop
git merge feature/AmazingFeature
git push origin develop

# Clean up local branch
git branch -d feature/AmazingFeature
```

### Deployments

To start a production deployment [create a PR from `develop` to `main`](https://github.com/djangonaut-space/wagtail-indymeet/compare/main...develop?title=Production%20Release%20-%20&body=PRs:%0A-%20) (bookmark this link for quick creation of PRs). The PR should follow this format:

```
Title: "Production release - <summary>"

Description:
PRs:
- #1
- #2
```

This should be merged with a merge commit. Merging to `main` branch deploys to [https://djangonaut.space](https://djangonaut.space).

Merging `feature/AmazingFeature` to `develop` deploys to [https://staging.djangonaut.space/](https://staging.djangonaut.space/)

`main` requires a linear commit history. This means if you make a change directly to `main`,
the `develop` branch must be rebased on `main`. Committing directly to main should only
occur in rare cases where a change must be pushed out to production immediately.

## Running `production` or `staging` locally

**Running production or staging locally**
- Set .env variables `USER`, `PASSWORD` and `HOST` for either `staging` or `production` in order to access staging db. Credentials are in the password manager
- `python manage.py runserver --settings=indymeet.settings.production`

**Migrate production or staging db**
- Set terminal variables for `USER`, `PASSWORD` and `HOST` for either `staging` or `production` db. Credentials are in the password manager.
- `python manage.py migrate --settings=indymeet.settings.production`

### Updating dependencies
This project uses [`pip-tools`](https://github.com/jazzband/pip-tools) to manage
dependencies. Most dependencies should be updated via Dependabot, but if they need
to be updated manually you would need to run `pip-compile --upgrade ...`. The rest of
the command can be found in the particular `requirements/*.txt` file you'd like to
update.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- LICENSE -->
## License

Distributed under the MIT License. See `LICENSE.txt` for more information.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- CONTACT -->
## Contact

- Dawn Wages - [@dawnwagessays](https://twitter.com/bajoranengineer) - [@bajoranengineer@mastodon.online](https://mastodon.online/@bajoranengineer)
- [Djangonaut Space Organizers](mailto:contact@djangonaut.space)


<p align="right">(<a href="#readme-top">back to top</a>)</p>
