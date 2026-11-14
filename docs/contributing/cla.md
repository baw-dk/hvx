# Why HVX has a Contributor License Agreement

HVX is open source under the [MPL-2.0](../../LICENSE). Before a first contribution
is merged, each contributor signs the [HVX Contributor License Agreement](../../CLA.md)
once.

## Why

The CLA lets the maintainer offer HVX under other terms *in addition to* MPL-2.0,
for example a commercial license for organisations that cannot accept MPL's
file-level copyleft. That is how the project can be funded without closing it.

It is a **license, not a copyright transfer**: you keep ownership of your work.
In return, the maintainer commits to keep your contributions available under
MPL-2.0 or another OSI-approved license and to keep your attribution (CLA §5).

## How to sign

1. Open a pull request. The **CLA** check reports whether every commit author has
   signed. If not, it comments on the pull request.
2. Reply on the pull request with exactly:

   ```
   I have read the CLA Document and I hereby sign the CLA
   ```

3. The check turns green. You are not asked again on later pull requests.

To re-run the check (for example after linking an email address to your GitHub
account), comment `recheck`.

Email and signed-document routes are described at the end of [CLA.md](../../CLA.md).

## Where signatures are stored

GitHub signatures are public, on the `cla-signatures` branch of the repository
(`signatures/version1/cla.json`): GitHub username, account id, pull request and
date. Email and PDF signatures are kept privately by the maintainer, who adds
only your GitHub account to the public record so the check recognises you.

## FAQ

**I did this work for my employer or my own company.** The company must agree
too. Ask in your pull request for the corporate agreement.

**Someone else's commits are in my pull request.** Every commit author must sign.
If a commit's email is not linked to any GitHub account, the check cannot match
it: link the email to your account and comment `recheck`, or re-author the commit.

**What about `Co-authored-by:` lines?** The check looks at commit authors. Human
co-authors should still sign. AI coding assistants credited as co-authors do not
sign; the human who submits the work is responsible for it (CLA §4).

**The CLA changes.** A new version applies only to contributions made after you
sign it; earlier signatures keep covering earlier contributions.
