<a name="readme-top"></a>
<!--
*** build from Best-README-Template.
-->



<!-- PROJECT SHIELDS -->
<!-- [![Contributors][contributors-shield]][contributors-url]
[![Forks][forks-shield]][forks-url]
[![Stargazers][stars-shield]][stars-url]
[![Issues][issues-shield]][issues-url]
[![MIT License][license-shield]][license-url] -->



<!-- PROJECT LOGO -->
<br />
<div align="center">
  <a href="https://github.com/dawnwages/wagtail-indymeet/">
    <img src="indymeet/static/img/wagtail.png" alt="Wagtail Logo" width="80" height="80">
  </a>

  <h3 align="center">Wagtail IndyMeet</h3>

  <p align="center">
    A Wagtail CMS clone of <a href="https://contributing.today">contributing today »</a>
    <br />
    <br />
    <br />
    <a href="">Demo - coming soon</a>
    ·
    <a href="">Report Bug</a>
    ·
    <a href="">Request Feature</a>
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
* [![Bootstrap][Bootstrap.com]][Bootstrap-url]
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
   $ source venv/bin/activate
   ```
   activate in Windows:
   ```sh
   > venv\Scripts\activate
   ```
3. install requirements:
   ```sh
   $ pip install -r requirements/requirements-dev.txt
   ```
4. Create a posgresql database **if you want to use quick and dirty SQLite db, set your `ENVIRONMENT` variable to `dev` (path not actively supported)**
   ```sh
   $ psql -u posgres
   ```
   ```sh
   postgres=# CREATE DATABASE local_djangonaut_space;
   CREATE DATABASE
   ```
   ```sh
   postgres=# exit
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
   ```python
   python manage.py migrate
   ```
   ```python
   python manage.py createsuperuser
   ```
7. Run locally
   ```python
   python manage.py runserver
   ```

<p align="right">(<a href="#readme-top">back to top</a>)</p>




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

Dawn Wages - [@dawnwagessays](https://twitter.com/dawnwagessays) - [@fly00gemini8712@mastodon.online](https://mastodon.online/@fly00gemini8712)


<p align="right">(<a href="#readme-top">back to top</a>)</p>