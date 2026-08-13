#![allow(clippy::disallowed_methods, reason = "tooling is exempt")]
use std::{env, ffi::OsString, process::Command};

use anyhow::{Context as _, Result, bail};
use clap::{Parser, ValueEnum};

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq, ValueEnum)]
enum VerificationProfile {
    #[default]
    Fast,
    Ci,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Check {
    id: &'static str,
    args: &'static [&'static str],
}

#[derive(Parser)]
pub struct ZeitgeistVerifyArgs {
    #[arg(long, value_enum, default_value = "fast")]
    profile: VerificationProfile,
}

fn checks(profile: VerificationProfile) -> Vec<Check> {
    let mut checks = vec![Check {
        id: "format",
        args: &["fmt", "--all", "--", "--check"],
    }];

    if profile == VerificationProfile::Ci {
        checks.push(Check {
            id: "xtask-clippy",
            args: &["xtask", "clippy", "--package", "xtask"],
        });
    }

    checks.extend([
        Check {
            id: "xtask-tests",
            args: &["test", "-p", "xtask"],
        },
        Check {
            id: "workflow-validation",
            args: &["xtask", "check-workflows"],
        },
    ]);
    checks
}

#[cfg(any(windows, test))]
fn run_format_packages<I, S, F>(packages: I, mut execute: F) -> Result<()>
where
    I: IntoIterator<Item = S>,
    S: AsRef<str>,
    F: FnMut(&[String]) -> Result<()>,
{
    for package in packages {
        let package = package.as_ref();
        let args = vec![
            "fmt".to_string(),
            "-p".to_string(),
            package.to_string(),
            "--".to_string(),
            "--check".to_string(),
        ];
        execute(&args)
            .with_context(|| format!("format failed for workspace package `{package}`"))?;
    }
    Ok(())
}

fn run_checks<F>(profile: VerificationProfile, mut execute: F) -> Result<()>
where
    F: FnMut(&Check) -> Result<()>,
{
    for check in checks(profile) {
        execute(&check)
            .with_context(|| format!("Zeitgeist verification check `{}` failed", check.id))?;
    }
    Ok(())
}

#[cfg(windows)]
fn run_workspace_format(cargo: &OsString) -> Result<()> {
    let workspace = crate::workspace::load_workspace()?;
    let mut packages = workspace
        .workspace_packages()
        .into_iter()
        .map(|package| package.name.to_string())
        .collect::<Vec<_>>();
    packages.sort();

    run_format_packages(packages, |args| {
        let status = Command::new(cargo)
            .args(args)
            .status()
            .context("failed to spawn package-wise cargo fmt")?;
        if !status.success() {
            bail!("command exited with {status}");
        }
        Ok(())
    })
}

fn run_check(cargo: &OsString, check: &Check) -> Result<()> {
    eprintln!("==> {}", check.id);
    #[cfg(windows)]
    if check.id == "format" {
        return run_workspace_format(cargo);
    }
    let status = Command::new(cargo)
        .args(check.args)
        .status()
        .context("failed to spawn cargo verification command")?;
    if !status.success() {
        bail!("command exited with {status}");
    }
    Ok(())
}

pub fn run(args: ZeitgeistVerifyArgs) -> Result<()> {
    let cargo = env::var_os("CARGO").unwrap_or_else(|| OsString::from("cargo"));
    run_checks(args.profile, |check| run_check(&cargo, check))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ids(profile: VerificationProfile) -> Vec<&'static str> {
        checks(profile).into_iter().map(|check| check.id).collect()
    }

    #[test]
    fn fast_profile_contains_deterministic_local_checks() {
        assert_eq!(
            ids(VerificationProfile::Fast),
            ["format", "xtask-tests", "workflow-validation"]
        );
    }

    #[test]
    fn ci_profile_adds_xtask_clippy() {
        assert_eq!(
            ids(VerificationProfile::Ci),
            [
                "format",
                "xtask-clippy",
                "xtask-tests",
                "workflow-validation"
            ]
        );
    }

    #[test]
    fn formats_windows_workspace_packages_with_separate_commands() {
        let mut commands = Vec::new();
        run_format_packages(["alpha", "beta"], |args| {
            commands.push(args.to_vec());
            Ok(())
        })
        .expect("package-wise format plan should succeed");

        assert_eq!(
            commands,
            [
                ["fmt", "-p", "alpha", "--", "--check"],
                ["fmt", "-p", "beta", "--", "--check"]
            ]
        );
    }

    #[test]
    fn cli_defaults_to_fast_profile() {
        let args = ZeitgeistVerifyArgs::try_parse_from(["zeitgeist-verify"])
            .expect("default verifier arguments should parse");
        assert_eq!(args.profile, VerificationProfile::Fast);
    }

    #[test]
    fn stops_after_first_failed_check() {
        let mut seen = Vec::new();
        let error = run_checks(VerificationProfile::Ci, |check| {
            seen.push(check.id);
            if check.id == "xtask-clippy" {
                anyhow::bail!("synthetic failure");
            }
            Ok(())
        })
        .expect_err("CI verification should stop on the synthetic failure");

        assert_eq!(seen, ["format", "xtask-clippy"]);
        assert!(error.to_string().contains("xtask-clippy"));
    }
}
