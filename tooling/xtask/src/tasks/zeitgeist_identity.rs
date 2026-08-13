use std::{
    env, fs,
    path::{Path, PathBuf},
};

use anyhow::{Context as _, Result, bail};
use clap::Parser;

const ARCHITECTURE_LINK: &str = "./docs/architecture/zeitgeist-product-architecture.md";
const ARCHITECTURE_PATH: &str = "docs/architecture/zeitgeist-product-architecture.md";
const REQUIRED_ARCHITECTURE_HEADINGS: &[&str] = &[
    "## Product statement",
    "## Foundations",
    "## Compatibility model",
    "## Current evidence-backed baseline",
    "## Product boundary",
    "## Development-system boundary",
    "## Non-goals",
    "## Decision test",
];

#[derive(Default, Parser)]
pub struct ZeitgeistIdentityArgs {}

fn first_non_empty_line(text: &str) -> Option<&str> {
    text.lines()
        .find(|line| !line.trim().is_empty())
        .map(str::trim)
}

fn validate_readme(readme: &str) -> Result<()> {
    let first_line = first_non_empty_line(readme).context("README.md is empty")?;
    if first_line != "# Zeitgeist" {
        bail!("README.md must begin with `# Zeitgeist`, found `{first_line}`");
    }
    if !readme.contains(ARCHITECTURE_LINK) {
        bail!("README.md must link to `{ARCHITECTURE_LINK}`");
    }
    Ok(())
}

fn validate_architecture(architecture: &str) -> Result<()> {
    let first_line = first_non_empty_line(architecture)
        .context("Zeitgeist product architecture document is empty")?;
    if first_line != "# Zeitgeist Product Architecture" {
        bail!(
            "Zeitgeist product architecture must begin with `# Zeitgeist Product Architecture`, found `{first_line}`"
        );
    }
    for required_heading in REQUIRED_ARCHITECTURE_HEADINGS {
        if !architecture
            .lines()
            .any(|line| line.trim() == *required_heading)
        {
            bail!("Zeitgeist product architecture is missing `{required_heading}`");
        }
    }
    Ok(())
}

fn find_repository_root(start: &Path) -> Result<PathBuf> {
    for candidate in start.ancestors() {
        if candidate.join("README.md").is_file()
            && candidate.join("tooling/xtask/Cargo.toml").is_file()
        {
            return Ok(candidate.to_path_buf());
        }
    }
    bail!(
        "could not locate Zeitgeist repository root from {}",
        start.display()
    )
}

pub fn run(_: ZeitgeistIdentityArgs) -> Result<()> {
    let current_dir = env::current_dir().context("failed to determine current directory")?;
    let repository_root = find_repository_root(&current_dir)?;
    let readme = fs::read_to_string(repository_root.join("README.md"))
        .context("failed to read README.md")?;
    let architecture = fs::read_to_string(repository_root.join(ARCHITECTURE_PATH))
        .with_context(|| format!("failed to read {ARCHITECTURE_PATH}"))?;

    validate_readme(&readme)?;
    validate_architecture(&architecture)?;
    eprintln!("Zeitgeist project identity is canonical.");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    const VALID_README: &str =
        "# Zeitgeist\n\n[Architecture](./docs/architecture/zeitgeist-product-architecture.md)\n";
    const VALID_ARCHITECTURE: &str = "# Zeitgeist Product Architecture\n\n## Product statement\n## Foundations\n## Compatibility model\n## Current evidence-backed baseline\n## Product boundary\n## Development-system boundary\n## Non-goals\n## Decision test\n";

    #[test]
    fn rejects_inherited_zed_readme_title() {
        let readme = VALID_README.replacen("# Zeitgeist", "# Zed", 1);
        let error = validate_readme(&readme).expect_err("Zed title must be rejected");
        assert!(error.to_string().contains("# Zeitgeist"));
    }

    #[test]
    fn rejects_readme_without_canonical_architecture_link() {
        let error = validate_readme("# Zeitgeist\n").expect_err("missing link must fail");
        assert!(
            error
                .to_string()
                .contains("zeitgeist-product-architecture.md")
        );
    }

    #[test]
    fn rejects_architecture_without_development_system_boundary() {
        let architecture = VALID_ARCHITECTURE.replace("## Development-system boundary\n", "");
        let error = validate_architecture(&architecture)
            .expect_err("missing development-system boundary must fail");
        assert!(error.to_string().contains("## Development-system boundary"));
    }

    #[test]
    fn accepts_canonical_project_context() {
        validate_readme(VALID_README).expect("canonical README should pass");
        validate_architecture(VALID_ARCHITECTURE).expect("canonical architecture should pass");
    }
}
