# 0007. Review rules for contracts

Status: accepted (kickoff)

## Context

The kickoff plan wanted `contracts/` changes to need approval from all three people. GitHub CODEOWNERS cannot enforce "all owners": it requires approval from any one listed owner.

## Decision

- Branch protection on `main`: one approving review, CI must pass, no direct pushes. The repo owner sets this, since it needs admin rights.
- `CODEOWNERS` maps each folder to its owner once people have picked roles.
- PRs touching `contracts/` must tick the template checkbox "all three owners acknowledged", with a link to the comment or message where each one did. The reviewer checks it.
