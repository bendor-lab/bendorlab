# Bendor Lab website

The source for www.bendorlab.com. GitHub hosts it for free, and the site rebuilds itself whenever something is saved.

What runs by itself:

- **Publications** refresh every Monday from ORCID, Crossref and PubMed.
- **You get an email** (as a GitHub issue) when papers are added to or dropped from the list, so you can veto anything wrong, and when the weekly refresh fails.
- **Photos** uploaded from a phone are rotated upright, shrunk to web size, and stripped of hidden metadata such as GPS location.
- **Every 1 October** a checklist issue reminds you to update people, alumni and photos for the new academic year.

## What lives where

| To change | Edit |
|---|---|
| Lab members and alumni | `data/people.yml` |
| Publication settings (always include, hide, section) | `data/publications.yml` |
| Research text and themes (also the home page introduction) | `data/research.yml` |
| Join the lab page (and any funded vacancies) | `data/positions.yml` |
| Lab photos | `data/photos.yml` and images in `static/images/photos/` |
| Name, address, email, footer links | `data/site.yml` |
| Page layouts (HTML) | `templates/*.html` |
| Colours, fonts, spacing | `static/css/style.css` |

`data/publications.json` is written by the weekly update. Don't edit it by hand; use `data/publications.yml` instead.

## One-time setup (about 30 minutes, on a computer)

### 1. Put the files on GitHub
1. Create a free account at github.com if you don't have one.
2. Click **New repository**. Name it `bendorlab`, choose **Public**, and create it.
3. Click **uploading an existing file** and drag in everything from this folder.
   The hidden items `.github` and `.pages.yml` must be included. On a Mac, press Cmd+Shift+. in Finder to show them. If the `.github` folder will not upload, choose **Add file > Create new file**, type `.github/workflows/deploy.yml` as the name, and paste in that file's contents.
4. Click **Commit changes**.

### 2. Turn on GitHub Pages
1. In the repository, go to **Settings > Pages**.
2. Under **Build and deployment > Source**, choose **GitHub Actions**.
3. Open the **Actions** tab, select **Build and publish website**, and click **Run workflow**.
4. After a minute or two the site is live at `https://YOUR-USERNAME.github.io/bendorlab/`. Check it before moving the domain.

### 3. Point www.bendorlab.com at GitHub
1. In **Settings > Pages > Custom domain**, enter `www.bendorlab.com` and save.
2. Where the domain is managed (today that is Squarespace: **Domains > bendorlab.com > DNS settings**), remove the Squarespace defaults and add:

   | Type | Host | Value |
   |---|---|---|
   | CNAME | www | `YOUR-USERNAME.github.io` |
   | A | @ | `185.199.108.153` |
   | A | @ | `185.199.109.153` |
   | A | @ | `185.199.110.153` |
   | A | @ | `185.199.111.153` |
   | AAAA | @ | `2606:50c0:8000::153` |
   | AAAA | @ | `2606:50c0:8001::153` |
   | AAAA | @ | `2606:50c0:8002::153` |
   | AAAA | @ | `2606:50c0:8003::153` |

   The domain has no email records today, so nothing else needs to be kept.
3. Back in **Settings > Pages**, tick **Enforce HTTPS** once it becomes available (this can take up to 24 hours).
4. Recommended: verify the domain so no one else can claim it. Go to your GitHub profile **Settings > Pages > Add a domain** and add the TXT record it shows.

### 4. Stop paying Squarespace
1. Once the new site loads at www.bendorlab.com, cancel the Squarespace **website** subscription. Keep the domain registration until it has moved.
2. Optional, to cut the domain cost: move the domain to Cloudflare Registrar, which charges the wholesale price.
   1. Create a free Cloudflare account and **Add a site** for bendorlab.com. It copies the DNS records above; set each GitHub record to **DNS only** (grey cloud), because GitHub needs to see visitors directly to issue the HTTPS certificate.
   2. Change the nameservers at Squarespace to the two Cloudflare gives you.
   3. At Squarespace, turn off **Domain lock** and request the transfer code; enter it in Cloudflare under **Domain Registration > Transfer**. The transfer completes in about 5 days with no downtime.

## Emails from the site

GitHub emails the repository owner whenever the site opens an issue. You will see:

- **Publication list updated**: lists papers that were added automatically or dropped. Nothing to do if they are right; otherwise hide or restore them as described below. Close the issue once read.
- **Publication refresh problem**: ORCID, Crossref or PubMed could not be reached. The site keeps showing the last good list, and a partial outage can only add papers, never remove them. Repeated weeks add comments to the same issue rather than new ones.
- **Yearly website check**: a checklist each October.

If these emails do not arrive, check **Watch** is set to at least "Participating and @mentions" on the repository page, and that your GitHub notification email is current.

## Editing the site

### With forms (easiest)
1. Go to app.pagescms.org and sign in with GitHub.
2. Install the Pages CMS app on the `bendorlab` repository when asked.
3. Open the repository. The sidebar has **People**, **Publications**, **Research**, **Positions**, **Photos** and **Site settings**.
4. Make changes and click **Save**. The site updates about two minutes later.

Photos can be uploaded straight from a phone (JPEG, PNG or WebP). To add a lab member, open **People**, click **Add an entry** under current members, fill in name and role, and upload a photo. To move someone to alumni, delete their entry from current members and add them under alumni. Drag entries to reorder.

To let a lab manager or student edit, add them as a collaborator on the repository (**Settings > Collaborators**).

Saving from the forms rewrites the YAML file tidily, which removes the explanatory comments in it. Nothing else changes.

### Directly
Any file can be edited on github.com with the pencil icon. The HTML pages are in `templates/`; most of the wording is in `data/`.

## How the publication list works

Every Monday, and whenever anything is saved, the site looks for papers in three places:

1. your ORCID record (0000-0001-6621-793X)
2. Crossref records that carry your ORCID iD
3. PubMed papers by "Bendor D" with a UCL affiliation

Full details for each paper come from Crossref. Anything found automatically must list "Bendor D" as an author, which filters out papers you reviewed. Errata and duplicate versions are dropped, and a preprint disappears once its journal version is listed. If the databases cannot be reached, or return a much shorter list than before, the site keeps the last good list.

- **A paper is missing**: add its DOI under **Papers to always list**. This is most likely for papers from other institutions where you are a middle author.
- **Something shouldn't be there**: add its DOI under **Papers to hide**.
- **Wrong section**: add the DOI under **Papers to always list** with the right section.
- To refresh immediately, open **Actions > Build and publish website > Run workflow**.

Keeping your ORCID record current improves the automatic list. In ORCID, granting Crossref permission to update your record lets new papers appear without any action.

GitHub pauses scheduled jobs in repositories with no activity for 60 days. The workflow re-enables itself each week; if GitHub ever emails to say the schedule was disabled, open the Actions tab and click **Enable workflow**.

## Keeping it running long term

- **Give someone else access.** If the repository lives only in one personal account, the site depends on that account. Consider creating a free GitHub organization (for example `bendorlab`), moving the repository into it, and making the lab manager a second owner.
- **Keep the domain on auto-renew** with a card that will not expire unnoticed. A lapsed domain is the most common way lab websites disappear; the yearly checklist includes this.
- **Keep ORCID current.** Granting Crossref permission to update your ORCID record makes new papers appear without any action.

## Previewing on your own computer (optional)

```
pip install -r requirements.txt
python scripts/fetch_publications.py   # optional: refresh publications
python scripts/optimise_images.py      # optional: shrink photos
python build.py --serve                # then open http://localhost:8000
```

## Costs

- GitHub Pages hosting: free for public repositories
- Pages CMS (hosted editor): free
- Domain: about $10 a year at Cloudflare Registrar
