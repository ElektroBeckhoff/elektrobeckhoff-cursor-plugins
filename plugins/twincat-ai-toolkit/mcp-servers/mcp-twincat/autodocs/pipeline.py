"""Folder processing orchestration (public API)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from autodocs.markdown import write_or_update_markdown, write_readme_and_toc
from autodocs.parsers.dut import parse_tcDut
from autodocs.parsers.gvl import parse_tcGvl
from autodocs.parsers.itf import parse_tcItf
from autodocs.parsers.pou import parse_tcPou
from autodocs.reporting import AutodocsLogger
from autodocs.type_index import build_type_index
from autodocs.types import AutodocsReport


def process_folder(
    base_folder: Path,
    output_folder: Path,
    *,
    verbose: bool = True,
    write_log: bool = False,
    include_toc_timestamp: bool = False,
) -> AutodocsReport:
    """
    Recursively find all .TcPOU / .TcDUT / .TcGVL / .TcIO files under
    'base_folder' and write/update corresponding .md files under
    '<output_folder>/docs'.

    Additionally:
      - Writes/updates a top-level README.md with a link to docs/toc.md.
      - Writes/updates docs/toc.md with a clickable directory/file index.
      - Optionally writes a run log to docs/autodocs.log (default: disabled).
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    root_out = output_folder / "docs"
    root_out.mkdir(parents=True, exist_ok=True)

    logs_path = root_out / "autodocs.log"

    if write_log:
        # Clear log file at start of run (fresh start each time)
        try:
            logs_path.write_text("", encoding="utf-8")
        except Exception:
            pass  # Ignore if file doesn't exist yet

    logger = AutodocsLogger(verbose=verbose)

    start = datetime.now()
    created_files: list[Path] = []
    skipped_hidden = 0
    errors = 0

    logger.log("Start processing")
    logger.log(f"Source: {base_folder}")
    logger.log(f"Output root: {root_out}")

    # Build cross-reference index (maps lowercase type name → relative .md path)
    type_index = build_type_index(base_folder)
    logger.log(f"Type index: {len(type_index)} types indexed for cross-referencing")

    # Process all POU files
    for file_path in base_folder.rglob("*.TcPOU"):
        try:
            rel_path = file_path.relative_to(base_folder)
            pou_out_file = (root_out / rel_path).with_suffix(".md")

            logger.log(f"Parsing: {file_path}")
            parsed = parse_tcPou(file_path, type_index, pou_out_file, root_out)

            if not parsed:
                skipped_hidden += 1
                logger.log(f"Skipped hidden POU: {file_path}")
                continue

            pou_out_file.parent.mkdir(parents=True, exist_ok=True)

            created_new, replaced_keys, appended_keys = write_or_update_markdown(
                pou_out_file,
                parsed["title"],
                parsed["sections"],
            )

            created_files.append(pou_out_file)

            if created_new:
                logger.log(
                    f"Created: {pou_out_file} (sections: {', '.join(parsed['sections'].keys())})"
                )
            else:
                msg_parts = []
                if replaced_keys:
                    msg_parts.append(f"replaced={','.join(replaced_keys)}")
                if appended_keys:
                    msg_parts.append(f"appended={','.join(appended_keys)}")
                logger.log(
                    f"Updated: {pou_out_file} ({'; '.join(msg_parts) if msg_parts else 'no changes'})"
                )

        except Exception as ex:
            errors += 1
            logger.log(f"ERROR processing {file_path}: {ex}")

    # Process all DUT files
    for file_path in base_folder.rglob("*.TcDUT"):
        try:
            rel_path = file_path.relative_to(base_folder)
            dut_out_file = (root_out / rel_path).with_suffix(".md")

            logger.log(f"Parsing DUT: {file_path}")
            parsed = parse_tcDut(file_path, type_index, dut_out_file, root_out)

            if not parsed:
                skipped_hidden += 1
                logger.log(f"Skipped hidden DUT: {file_path}")
                continue

            dut_out_file.parent.mkdir(parents=True, exist_ok=True)

            created_new, replaced_keys, appended_keys = write_or_update_markdown(
                dut_out_file,
                parsed["title"],
                parsed["sections"],
            )

            created_files.append(dut_out_file)

            if created_new:
                logger.log(
                    f"Created: {dut_out_file} (sections: {', '.join(parsed['sections'].keys())})"
                )
            else:
                msg_parts = []
                if replaced_keys:
                    msg_parts.append(f"replaced={','.join(replaced_keys)}")
                if appended_keys:
                    msg_parts.append(f"appended={','.join(appended_keys)}")
                logger.log(
                    f"Updated: {dut_out_file} ({'; '.join(msg_parts) if msg_parts else 'no changes'})"
                )

        except Exception as ex:
            errors += 1
            logger.log(f"ERROR processing DUT {file_path}: {ex}")

    # Process all GVL files
    for file_path in base_folder.rglob("*.TcGVL"):
        try:
            rel_path = file_path.relative_to(base_folder)
            gvl_out_file = (root_out / rel_path).with_suffix(".md")

            logger.log(f"Parsing GVL: {file_path}")
            parsed = parse_tcGvl(file_path, type_index, gvl_out_file, root_out)

            if not parsed:
                skipped_hidden += 1
                logger.log(f"Skipped hidden GVL: {file_path}")
                continue

            gvl_out_file.parent.mkdir(parents=True, exist_ok=True)

            created_new, replaced_keys, appended_keys = write_or_update_markdown(
                gvl_out_file,
                parsed["title"],
                parsed["sections"],
            )

            created_files.append(gvl_out_file)

            if created_new:
                logger.log(
                    f"Created: {gvl_out_file} (sections: {', '.join(parsed['sections'].keys())})"
                )
            else:
                msg_parts = []
                if replaced_keys:
                    msg_parts.append(f"replaced={','.join(replaced_keys)}")
                if appended_keys:
                    msg_parts.append(f"appended={','.join(appended_keys)}")
                logger.log(
                    f"Updated: {gvl_out_file} ({'; '.join(msg_parts) if msg_parts else 'no changes'})"
                )

        except Exception as ex:
            errors += 1
            logger.log(f"ERROR processing GVL {file_path}: {ex}")

    # Process all Interface files
    for file_path in base_folder.rglob("*.TcIO"):
        try:
            rel_path = file_path.relative_to(base_folder)
            itf_out_file = (root_out / rel_path).with_suffix(".md")

            logger.log(f"Parsing ITF: {file_path}")
            parsed = parse_tcItf(file_path, type_index, itf_out_file, root_out)

            if not parsed:
                skipped_hidden += 1
                logger.log(f"Skipped hidden ITF: {file_path}")
                continue

            itf_out_file.parent.mkdir(parents=True, exist_ok=True)

            created_new, replaced_keys, appended_keys = write_or_update_markdown(
                itf_out_file,
                parsed["title"],
                parsed["sections"],
            )

            created_files.append(itf_out_file)

            if created_new:
                logger.log(
                    f"Created: {itf_out_file} (sections: {', '.join(parsed['sections'].keys())})"
                )
            else:
                msg_parts = []
                if replaced_keys:
                    msg_parts.append(f"replaced={','.join(replaced_keys)}")
                if appended_keys:
                    msg_parts.append(f"appended={','.join(appended_keys)}")
                logger.log(
                    f"Updated: {itf_out_file} ({'; '.join(msg_parts) if msg_parts else 'no changes'})"
                )

        except Exception as ex:
            errors += 1
            logger.log(f"ERROR processing ITF {file_path}: {ex}")

    # Write README and toc
    try:
        write_readme_and_toc(
            output_folder,
            root_out,
            created_files,
            timestamp,
            include_toc_timestamp=include_toc_timestamp,
        )
        logger.log("Wrote README.md and docs/toc.md")
    except Exception as ex:
        errors += 1
        logger.log(f"ERROR writing README/toc.md: {ex}")

    # Summary
    duration = (datetime.now() - start).total_seconds()
    summary = (
        f"Done. Created/Updated={len(created_files)}, "
        f"SkippedHidden={skipped_hidden}, Errors={errors}, "
        f"DurationSec={duration:.2f}"
    )
    logger.log(summary)

    # Write log file (ASCII-only status line — Windows console may not encode Unicode marks)
    if write_log:
        log_written = False
        try:
            header = [
                "-" * 60,
                f"Run: {timestamp}",
                f"Source: {base_folder}",
                f"Output: {root_out}",
                f"Summary: Created/Updated={len(created_files)}, SkippedHidden={skipped_hidden}, Errors={errors}",
                "-" * 60,
                "",
            ]
            with open(logs_path, "w", encoding="utf-8") as f:
                f.write("\n".join(header + logger.lines) + "\n")
            log_written = True
        except Exception as ex:
            if verbose:
                print(f"ERROR writing autodocs.log: {ex}")
        if verbose and log_written:
            print(f"Log written: {logs_path}")

    return AutodocsReport(
        success=errors == 0,
        files_created=[str(p) for p in created_files],
        skipped_hidden=skipped_hidden,
        errors=errors,
        duration_sec=duration,
        output=str(root_out),
        log_lines=list(logger.lines),
        timestamp=timestamp,
    )
