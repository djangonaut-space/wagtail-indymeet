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
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
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
* Python version 3.10.5

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
   psql -u posgres
   ```
   ```sh
   postgres=# CREATE DATABASE "djangonaut-space";
   CREATE DATABASE
   ```
   ```sh
   postgres=# exit
   ```
4. install requirements:
   ```sh
   pip install -r requirements/requirements-dev.txt
   python manage.py tailwind install
   ```

5. Copy `.env.template` file, rename to `.env` and use variables for your local postgres database.
   Copy in Linux:
   ```sh
   cp .env.template .env
   ```
   activate in Windows:
   ```sh
   copy .env.template .env
   ```
6. Run migrations and create superuser
   ```sh
   python manage.py migrate
   # Potentially load data first
   # python manage.py loaddata fixtures/data.json
   python manage.py createsuperuser
   ```
7. Run server locally
   ```sh
   python manage.py runserver
   ```
8. Run tailwind in another terminal locally
   ```sh
   python manage.py tailwind start
   ```

<p align="right">(<a href="#readme-top">back to top</a>)</p>


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


<!-- ROADMAP -->
## Roadmap

- [x] Add Changelog
- [x] Add back to top links
- [ ] Add Additional Templates w/ Examples
- [ ] Add "components" document to easily copy & paste sections of the readme
- [ ] Multi-language Support
    - [ ] Chinese
    - [ ] Spanish

See the [open issues](https://github.com/dawnwages/wagtail-indymeet/issues) for a full list of proposed features (and known issues).

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- CONTRIBUTING -->
## Contributing

Contributions are what make the open source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

If you have a suggestion that would make this better, please fork the repo and create a pull request. You can also simply open an issue with the tag "enhancement".
Don't forget to give the project a star! Thanks again!

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## Running `production` or `staging` locally
Merging to `main` branch deploys to [https://djangonaut.space](https://djangonaut.space). Merging `feature/AmazingFeature` to `develop` deploys to [https://staging-djangonaut-space.azurewebsites.net/](https://staging-djangonaut-space.azurewebsites.net/)

**Running production or staging locally**
- Set .env variables `USER`, `PASSWORD` and `HOST` for either `staging` or `production` in order to access staging db. Credentials are in the password manager
- `python manage.py runserver --settings=indymeet.settings.production`

**Migrate production or staging db**
- Set terminal variables for `USER`, `PASSWORD` and `HOST` for either `staging` or `production` db. Credentials are in the password manager.
- `python manage.py migrate --settings=indymeet.settings.production`

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- LICENSE -->
## License

Distributed under the MIT License. See `LICENSE.txt` for more information.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- CONTACT -->
## Contact

- Dawn Wages - [@dawnwagessays](https://twitter.com/dawnwagessays) - [@fly00gemini8712@mastodon.online](https://mastodon.online/@fly00gemini8712)
- [Djangonaut Space Organizers](mailto:contact@djangonaut.space)


<p align="right">(<a href="#readme-top">back to top</a>)</p>
