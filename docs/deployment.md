# Deployment

This page describes how to deploy the site.

The production and staging site exist on the same Hetzner
server. You may have access to the credentials in the
1Password account.

## Connecting to the server

1. Log into Hetzner account
2. Add your ssh key to Security -> Add SSH Key
3. Add your ssh key to ``~/.ssh/authorized_keys`` on the server (may need another person's help or use the Console in the web app)
4. ``ssh root@djangonaut.space`` or ``ssh root@staging.djangonaut.space`` (they go to the same place)

## Running a remote command

If you need to run a ``manage.py`` command on the server, connect to it
then run:

```
# Staging
dokku run staging -- python manage.py createsuperuser

# Production
dokku run djangonaut-space -- python manage.py createsuperuser
```

## Change environment variable

```
# Get config variables
dokku config staging
dokku config djangonaut-space

# Set config variable
dokku config:set staging KEY1="value1" KEY2="value2"
dokku config:set djangonaut-space KEY1="value1" KEY2="value2"
```

## View logs

```
# Staging
dokku logs -t staging

# Production
dokku logs -t djangonaut-space
```

## Deploying from your local machine

Ideally, this won't be necessary, and we'll still use deployments
via GitHub actions. You need to be able to connect to the server.

1. Add the remotes
  ```
  git remote add staging dokku@djangonaut.space:staging
  git remote add djangonaut-space dokku@djangonaut.space:djangonaut-space
  ```
2. Push local develop branch to staging
  ```
  git push staging develop
  ```
3. Push local feature branch to staging
  ```
  git push staging my-feature-branch:develop
  ```
4. Push local main branch to production
  ```
  git push djangonaut-space main
  ```
5. Push local main branch to production
  ```
  git push djangonaut-space my-feature-branch:main
  ```

## Configuring deployment key for CI/CD

On the server:

```bash
su dokku
ssh-keygen -t ed25519 -C "github-actions-deploy@djangonaut.space" -f ~/.ssh/dokku_deploy_key -N ""
exit
dokku ssh-keys:add deploy-<TODAYS_DATE> /home/dokku/.ssh/dokku_deploy_key.pub
cat /home/dokku/.ssh/dokku_deploy_key
rm /home/dokku/.ssh/dokku_deploy_key
rm /home/dokku/.ssh/dokku_deploy_key.pub
```

Copy the output of the secret key and update the ``DEPLOY_DOKKU_SSH_PRIVATE_KEY``
environment in the GitHub actions secrets.
