from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OpenSourceReleaseTests(unittest.TestCase):
    def test_entitlement_subsystem_is_removed(self):
        licensing_dir = ROOT / "backend" / "app" / "licensing"
        self.assertFalse(any(licensing_dir.glob("*.py")))
        self.assertFalse((ROOT / "frontend" / "src" / "license.jsx").exists())
        self.assertFalse(
            (ROOT / "frontend" / "src" / "components" / "UpgradeGate.jsx").exists()
        )

    def test_private_service_and_gate_markers_are_absent(self):
        checked_suffixes = {".py", ".js", ".jsx", ".md", ".json", ".example"}
        ignored = {
            ROOT / "CHANGELOG.md",
            ROOT / "CODEX_SESSION.md",
            ROOT / "docs" / "OPEN_SOURCE_RELEASE_CHECKLIST.md",
            Path(__file__).resolve(),
        }
        banned = (
            "license.adventcybersecurity.com",
            "feature_gated",
            "BREACHWRIGHT_LICENSE",
            "Professional license",
            "Community Edition",
            "UpgradeGate",
        )

        failures = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or path in ignored or path.suffix not in checked_suffixes:
                continue
            if ".git" in path.parts or "node_modules" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for marker in banned:
                if marker in text:
                    failures.append(f"{path.relative_to(ROOT)} contains {marker!r}")

        self.assertEqual([], failures)

    def test_attribution_and_license_files_exist(self):
        for name in ("LICENSE", "NOTICE", "TRADEMARKS.md", "SECURITY.md"):
            self.assertTrue((ROOT / name).is_file(), name)

        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Created by [Advent Cybersecurity]", readme)
        self.assertIn("Apache License 2.0", readme)

    def test_local_service_rejects_untrusted_host_headers(self):
        main = (ROOT / "backend" / "app" / "main.py").read_text(
            encoding="utf-8"
        )
        packaged_smoke = (ROOT / "scripts" / "smoke_bundle.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("TrustedHostMiddleware", main)
        self.assertIn(
            'allowed_hosts=["127.0.0.1", "localhost", "testserver"]',
            main,
        )
        self.assertIn('headers={"Host": "rebind.attacker.example"}', packaged_smoke)

    def test_local_workspace_has_no_account_or_token_surface(self):
        reports_router = (
            ROOT / "backend" / "app" / "reports" / "router.py"
        ).read_text(encoding="utf-8")
        evidence_router = (
            ROOT / "backend" / "app" / "findings" / "evidence.py"
        ).read_text(encoding="utf-8")
        frontend_api = (ROOT / "frontend" / "src" / "api.js").read_text(
            encoding="utf-8"
        )
        frontend_app = (ROOT / "frontend" / "src" / "App.jsx").read_text(
            encoding="utf-8"
        )
        frontend_layout = (
            ROOT / "frontend" / "src" / "components" / "Layout.jsx"
        ).read_text(encoding="utf-8")
        frontend_settings = (
            ROOT / "frontend" / "src" / "pages" / "Settings.jsx"
        ).read_text(encoding="utf-8")
        installers = (
            (ROOT / "install-windows.bat").read_text(encoding="utf-8"),
            (ROOT / "install.sh").read_text(encoding="utf-8"),
            (ROOT / "INSTALL_WSL.md").read_text(encoding="utf-8"),
        )

        main = (ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
        requirements = (ROOT / "backend" / "requirements.txt").read_text(
            encoding="utf-8"
        )

        for path in (
            ROOT / "backend" / "app" / "auth" / "router.py",
            ROOT / "backend" / "app" / "auth" / "service.py",
            ROOT / "frontend" / "src" / "pages" / "Login.jsx",
            ROOT / "frontend" / "src" / "pages" / "Setup.jsx",
        ):
            self.assertFalse(path.exists(), path)

        self.assertNotIn("auth_router", main)
        self.assertNotIn("Authorization", frontend_api)
        self.assertNotIn("accessToken", frontend_api)
        self.assertNotIn("import('./pages/Login')", frontend_app)
        self.assertNotIn("import('./pages/Setup')", frontend_app)
        self.assertNotIn("Logout", frontend_layout)
        self.assertNotIn("User Management", frontend_settings)
        self.assertNotIn("Change Password", frontend_settings)
        for installer in installers:
            self.assertNotIn("--setup", installer)
            self.assertNotIn("Create your admin account", installer)
            self.assertIn("Advent Cybersecurity", installer)
            self.assertIn("open source", installer.lower())
        self.assertNotIn("PyJWT", requirements)
        self.assertNotIn("passlib", requirements)
        self.assertNotIn("token: str = None", reports_router)
        self.assertIn(
            "current_user: User = Depends(get_current_user)",
            reports_router,
        )
        self.assertIn(
            "current_user: User = Depends(get_current_user)",
            evidence_router,
        )
        self.assertNotIn(
            '@app.get("/api/evidence/{attachment_id}/file")',
            main,
        )

    def test_docx_generation_runs_off_event_loop(self):
        reports_router = (
            ROOT / "backend" / "app" / "reports" / "router.py"
        ).read_text(encoding="utf-8")

        self.assertIn("await asyncio.to_thread(", reports_router)
        self.assertIn("generate_docx_report,", reports_router)

    def test_chat_content_is_not_rendered_as_raw_html(self):
        assistant = (
            ROOT / "frontend" / "src" / "pages" / "Assistant.jsx"
        ).read_text(encoding="utf-8")
        self.assertNotIn("dangerouslySetInnerHTML", assistant)

    def test_frontend_assets_use_server_root_for_deep_links(self):
        vite_config = (ROOT / "frontend" / "vite.config.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("base: '/'", vite_config)
        self.assertNotIn("base: './'", vite_config)

    def test_fixed_sidebar_does_not_force_horizontal_overflow(self):
        layout = (
            ROOT / "frontend" / "src" / "components" / "Layout.jsx"
        ).read_text(encoding="utf-8")
        engagement_page = (
            ROOT / "frontend" / "src" / "pages" / "EngagementDetail.jsx"
        ).read_text(encoding="utf-8")
        self.assertIn('className="min-w-0 flex-1 ml-60"', layout)
        self.assertIn('className="flex mb-6 overflow-x-auto"', engagement_page)
        self.assertIn('className="flex-1 min-w-0 h-40"', engagement_page)
        self.assertIn(
            'className="flex flex-col lg:flex-row lg:items-center justify-between',
            engagement_page,
        )

    def test_coverage_methods_load_in_an_effect(self):
        coverage_review = (
            ROOT / "frontend" / "src" / "components" / "GapAnalysisTab.jsx"
        ).read_text(encoding="utf-8")
        self.assertIn("useEffect(() => {", coverage_review)
        self.assertIn("[engId, toast]", coverage_review)
        self.assertNotIn("useState(() => {\n    gapAnalysis.methodologies", coverage_review)
        self.assertNotIn("methodologies(engId).then(setMethodologies).catch(() => {})", coverage_review)

    def test_primary_workspace_load_failures_are_visible(self):
        pages = (
            ROOT / "frontend" / "src" / "pages" / "Dashboard.jsx",
            ROOT / "frontend" / "src" / "pages" / "Assistant.jsx",
            ROOT / "frontend" / "src" / "pages" / "KnowledgeBase.jsx",
            ROOT / "frontend" / "src" / "pages" / "EngagementDetail.jsx",
        )
        for path in pages:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("catch(() => {})", source, path)

    def test_generated_report_inputs_do_not_use_em_dashes(self):
        for path in (
            ROOT / "backend" / "app" / "narrative" / "service.py",
            ROOT / "backend" / "app" / "correlation" / "engine.py",
            ROOT / "backend" / "app" / "gap_detection" / "service.py",
        ):
            self.assertNotIn("—", path.read_text(encoding="utf-8"), path)

    def test_docker_application_data_is_persistent(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("- DATA_DIR=/app/data", compose)
        self.assertIn("- ./data:/app/data", compose)
        self.assertNotIn("./data/uploads:/app/data/uploads", compose)
        self.assertNotIn("./data/reports:/app/data/reports", compose)
        self.assertIn('- "127.0.0.1:80:80"', compose)
        self.assertNotIn('- "13370:13370"', compose)

        launcher = (ROOT / "run.py").read_text(encoding="utf-8")
        self.assertIn('choices=("127.0.0.1", "localhost")', launcher)

    def test_upload_routes_do_not_read_unbounded_requests(self):
        upload_routes = (
            ROOT / "backend" / "app" / "analysis" / "router.py",
            ROOT / "backend" / "app" / "findings" / "evidence.py",
            ROOT / "backend" / "app" / "reports" / "template_router.py",
            ROOT / "backend" / "app" / "ad" / "router.py",
            ROOT / "backend" / "app" / "engagements" / "export_import.py",
            ROOT / "backend" / "app" / "workflow" / "template_router.py",
            ROOT / "backend" / "app" / "findings" / "template_router.py",
            ROOT / "backend" / "app" / "findings" / "notebook_router.py",
        )
        for path in upload_routes:
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("await file.read()", source, path)
            self.assertNotIn("await logo.read()", source, path)

    def test_ai_analysis_scan_set_and_reads_are_bounded(self):
        source = (
            ROOT / "backend" / "app" / "analysis" / "router.py"
        ).read_text(encoding="utf-8")
        self.assertIn("MAX_ANALYSIS_SCANS = 50", source)
        self.assertIn("MAX_ANALYSIS_TOTAL_BYTES = 250 * 1024 * 1024", source)
        self.assertIn(".limit(MAX_ANALYSIS_SCANS + 1)", source)
        self.assertIn("source.read(MAX_SCAN_SIZE + 1)", source)

    def test_workspace_overview_sections_fail_independently(self):
        source = (
            ROOT / "frontend" / "src" / "components" / "WorkspaceOverviewTab.jsx"
        ).read_text(encoding="utf-8")
        self.assertIn("Promise.allSettled", source)
        self.assertIn("Overview loaded with unavailable sections", source)
        engagement_page = (
            ROOT / "frontend" / "src" / "pages" / "EngagementDetail.jsx"
        ).read_text(encoding="utf-8")
        self.assertIn("event.key.toLowerCase() === 'k'", engagement_page)
        self.assertIn("useState('overview')", engagement_page)

    def test_bundle_verifier_is_portable_and_argument_driven(self):
        source = (ROOT / "verify_bundle.py").read_text(encoding="utf-8")
        self.assertIn('parser.add_argument(', source)
        self.assertIn('default=PROJECT_ROOT / "dist" / "Breachwright"', source)
        self.assertNotIn('expanduser("~/Desktop', source)
        self.assertNotIn("â", source)

    def test_packaged_cli_exposes_read_only_backup_validation(self):
        launcher = (ROOT / "run.py").read_text(encoding="utf-8")
        smoke = (ROOT / "scripts" / "smoke_bundle.py").read_text(encoding="utf-8")
        self.assertIn('"--validate-backup"', launcher)
        self.assertIn("manifest = validate_backup", launcher)
        self.assertIn("Backup validation failed:", launcher)
        self.assertIn('[str(cli), "--validate-backup"', smoke)

    def test_backup_verification_stays_responsive_and_surfaces_failures(self):
        router = (ROOT / "backend" / "app" / "system" / "router.py").read_text(
            encoding="utf-8"
        )
        settings = (ROOT / "frontend" / "src" / "pages" / "Settings.jsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("await asyncio.to_thread(_list_backup_metadata", router)
        self.assertIn("await asyncio.to_thread(validate_backup", router)
        self.assertIn('"valid": False', router)
        self.assertIn("failed verification", settings)
        self.assertIn("protected file", settings)

    def test_support_snapshot_has_a_bounded_privacy_contract(self):
        router = (ROOT / "backend" / "app" / "system" / "router.py").read_text(
            encoding="utf-8"
        )
        frontend = (ROOT / "frontend" / "src" / "pages" / "Settings.jsx").read_text(
            encoding="utf-8"
        )
        smoke = (ROOT / "scripts" / "smoke_bundle.py").read_text(encoding="utf-8")
        self.assertIn('diagnostic_data.pop("data_directory", None)', router)
        self.assertIn('"contains_logs": False', router)
        self.assertIn('"contains_credentials": False', router)
        self.assertIn('"contains_workspace_content": False', router)
        self.assertIn("Support snapshots exclude logs", frontend)
        self.assertIn('client.get("/api/system/support-snapshot"', smoke)

    def test_tool_runner_analysis_is_scoped_and_history_is_bounded(self):
        router = (ROOT / "backend" / "app" / "jobs" / "router.py").read_text(
            encoding="utf-8"
        )
        frontend = (ROOT / "frontend" / "src" / "pages" / "ToolRunner.jsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("limit: int = Query(default=50, ge=1, le=200)", router)

    def test_tool_runner_presets_are_server_built_and_custom_commands_are_explicit(self):
        router = (ROOT / "backend" / "app" / "jobs" / "router.py").read_text(
            encoding="utf-8"
        )
        frontend = (ROOT / "frontend" / "src" / "pages" / "ToolRunner.jsx").read_text(
            encoding="utf-8"
        )
        runner = (ROOT / "backend" / "app" / "jobs" / "runner.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('execution_mode: Literal["preset", "custom"]', router)
        self.assertIn("SAFE_PRESET_TARGET.fullmatch(target)", router)
        self.assertIn("command = _build_job_command(body)", router)
        self.assertIn("execution_mode: 'preset'", frontend)
        self.assertIn("execution_mode: 'custom'", frontend)
        self.assertIn("Run this custom command with your local shell?", frontend)
        self.assertNotIn('logger.info("Starting job %s: %s"', runner)
        smoke = (ROOT / "scripts" / "smoke_bundle.py").read_text(encoding="utf-8")
        self.assertIn('"target": "192.0.2.55 && whoami"', smoke)
        self.assertIn("rejected_preset.status_code != 422", smoke)
        self.assertIn(".limit(limit)", router)
        self.assertIn("analysisApi.run(selectedEng, [scanId])", frontend)
        self.assertIn("window.confirm(confirmation)", frontend)
        self.assertIn("Stop &amp; Delete", frontend)

    def test_assistant_context_and_citations_are_bounded_before_provider_use(self):
        router = (ROOT / "backend" / "app" / "assistant" / "router.py").read_text(
            encoding="utf-8"
        )
        frontend = (ROOT / "frontend" / "src" / "pages" / "Assistant.jsx").read_text(
            encoding="utf-8"
        )
        privacy_notice = (ROOT / "frontend" / "src" / "components" / "AIProviderNotice.jsx").read_text(
            encoding="utf-8"
        )
        self.assertIn('raise HTTPException(status_code=404, detail="Engagement not found")', router)
        self.assertIn(".limit(MAX_ASSISTANT_SCANS)", router)
        self.assertIn(".limit(MAX_ASSISTANT_AD_PATHS)", router)
        self.assertIn("citations_present_in_context", router)
        self.assertIn("citation_ids_in_order(response)", router)
        self.assertIn("AIProviderNotice", frontend)
        self.assertIn("disabled={sending || !providerConfig", frontend)
        self.assertIn("Local secret redaction:", privacy_notice)
        self.assertIn("may send bounded engagement context", privacy_notice)
        self.assertIn("await asyncio.to_thread(", router)
        self.assertIn("read_scan_excerpt", router)
        self.assertIn("bounded_context_value(f.evidence", router)
        self.assertNotIn('f.read()[:3000]', router)

    def test_stored_report_and_attachment_deletions_are_explicit_and_retryable(self):
        report_router = (ROOT / "backend" / "app" / "reports" / "router.py").read_text(
            encoding="utf-8"
        )
        evidence_router = (ROOT / "backend" / "app" / "findings" / "evidence.py").read_text(
            encoding="utf-8"
        )
        notebook_router = (ROOT / "backend" / "app" / "findings" / "notebook_router.py").read_text(
            encoding="utf-8"
        )
        scan_router = (ROOT / "backend" / "app" / "analysis" / "router.py").read_text(
            encoding="utf-8"
        )
        job_router = (ROOT / "backend" / "app" / "jobs" / "router.py").read_text(
            encoding="utf-8"
        )
        engagement_page = (ROOT / "frontend" / "src" / "pages" / "EngagementDetail.jsx").read_text(
            encoding="utf-8"
        )
        notebook_page = (ROOT / "frontend" / "src" / "components" / "EvidenceNotebookTab.jsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("Report file could not be removed", report_router)
        self.assertIn("Evidence file could not be removed", evidence_router)
        self.assertIn("Notebook attachment could not be removed", notebook_router)
        self.assertIn("Scan file could not be removed", scan_router)
        self.assertIn("Tool Runner output could not be removed", job_router)
        self.assertIn("await db.flush()", scan_router)
        self.assertNotIn('could not be removed: {exc}', report_router)
        self.assertNotIn('could not be removed: {exc}', evidence_router)
        self.assertNotIn('could not be removed: {exc}', notebook_router)
        self.assertNotIn('could not be removed: {exc}', scan_router)
        self.assertNotIn('could not be removed: {exc}', job_router)
        self.assertIn('Delete generated report', engagement_page)
        self.assertIn('Delete evidence attachment', engagement_page)
        self.assertIn('Delete notebook attachment', notebook_page)

    def test_ai_reports_have_a_provider_free_privacy_preflight(self):
        report_router = (ROOT / "backend" / "app" / "reports" / "router.py").read_text(
            encoding="utf-8"
        )
        engagement_page = (ROOT / "frontend" / "src" / "pages" / "EngagementDetail.jsx").read_text(
            encoding="utf-8"
        )
        self.assertIn('reports/ai-preflight', report_router)
        self.assertIn('"redaction_enabled": settings.ai_redact_sensitive_data', report_router)
        self.assertIn('"external_provider": provider not in', report_router)
        self.assertIn('AI report preflight', engagement_page)
        self.assertIn('External provider usage may incur charges.', engagement_page)
        self.assertIn('Sensitive-data redaction is off.', engagement_page)
        self.assertIn('AI report preflight unavailable:', engagement_page)
        self.assertIn('disabled={!aiPreflight}', engagement_page)
        self.assertNotIn('detail=f"AI provider error: {e}"', report_router)

    def test_ai_actions_show_privacy_state_and_fail_closed_when_it_is_unavailable(self):
        notice = (ROOT / "frontend" / "src" / "components" / "AIProviderNotice.jsx").read_text(
            encoding="utf-8"
        )
        engagement_page = (ROOT / "frontend" / "src" / "pages" / "EngagementDetail.jsx").read_text(
            encoding="utf-8"
        )
        coverage_page = (ROOT / "frontend" / "src" / "components" / "GapAnalysisTab.jsx").read_text(
            encoding="utf-8"
        )
        assistant_page = (ROOT / "frontend" / "src" / "pages" / "Assistant.jsx").read_text(
            encoding="utf-8"
        )
        tool_runner = (ROOT / "frontend" / "src" / "pages" / "ToolRunner.jsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("AI privacy settings unavailable:", notice)
        self.assertIn("External provider usage may incur charges.", notice)
        self.assertIn("onConfigChange(null)", notice)
        self.assertIn("confirmAIAction", engagement_page)
        self.assertIn("confirmAIAction", coverage_page)
        self.assertIn("confirmAIAction", assistant_page)
        self.assertIn("analysisApi.preview(selectedEng, [scanId])", tool_runner)
        self.assertIn("disabled={job._analyzing || !aiReady}", tool_runner)
        self.assertIn("setAnalysisPreview(null)", engagement_page)

    def test_ai_provider_failures_do_not_echo_raw_provider_responses(self):
        ai_workflows = (
            ROOT / "backend" / "app" / "analysis" / "router.py",
            ROOT / "backend" / "app" / "assistant" / "router.py",
            ROOT / "backend" / "app" / "attack_paths" / "router.py",
            ROOT / "backend" / "app" / "ad" / "router.py",
            ROOT / "backend" / "app" / "gap_detection" / "service.py",
            ROOT / "backend" / "app" / "narrative" / "service.py",
            ROOT / "backend" / "app" / "reports" / "router.py",
        )
        for path in ai_workflows:
            source = path.read_text(encoding="utf-8")
            self.assertIn("AI_PROVIDER_FAILURE_MESSAGE", source, path)
            self.assertNotIn('detail=f"AI provider error:', source, path)
            self.assertNotIn('detail=f"AI analysis failed:', source, path)
            self.assertNotIn('return {"error": f"AI provider error:', source, path)
            self.assertNotIn('logger.error("AI provider', source, path)

    def test_exploitation_chain_inputs_and_outputs_are_explicitly_bounded(self):
        router = (ROOT / "backend" / "app" / "attack_paths" / "router.py").read_text(
            encoding="utf-8"
        )
        validation = (ROOT / "backend" / "app" / "ai" / "output_validation.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("MAX_ATTACK_PATH_FINDINGS = 200", router)
        self.assertIn(".limit(MAX_ATTACK_PATH_FINDINGS + 1)", router)
        self.assertIn("MAX_ATTACK_PATH_DESCRIPTION_CHARS", router)
        self.assertIn("MAX_ATTACK_PATH_SCOPE_CHARS", router)
        self.assertIn("MAX_AI_ATTACK_PATHS = 25", validation)
        self.assertIn("MAX_AI_AD_PATHS = 100", validation)

    def test_no_ai_correlation_uses_bounded_worker_thread_reads(self):
        router = (ROOT / "backend" / "app" / "correlation" / "router.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("MAX_CORRELATION_SCANS = 50", router)
        self.assertIn("MAX_CORRELATION_FILE_BYTES = 50 * 1024 * 1024", router)
        self.assertIn("MAX_CORRELATION_TOTAL_BYTES = 250 * 1024 * 1024", router)
        self.assertIn("await asyncio.to_thread(", router)
        self.assertIn(".limit(MAX_CORRELATION_SCANS + 1)", router)
        self.assertNotIn("raw = f.read()", router)

    def test_active_directory_import_refreshes_current_paths_and_confirms_deletion(self):
        page = (ROOT / "frontend" / "src" / "pages" / "EngagementDetail.jsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("Delete ${adImport.filename}", page)
        self.assertIn("adApi.deleteImport(engId, adImport.id)", page)
        self.assertGreaterEqual(page.count("adApi.paths(engId)"), 3)
        self.assertIn("setPaths(currentPaths)", page)

        parser = (ROOT / "backend" / "app" / "ad" / "parser.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("objects_by_id = {", parser)
        self.assertNotIn("next((o for o in result.objects", parser)

        router = (ROOT / "backend" / "app" / "ad" / "router.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("created_at=datetime.now(timezone.utc)", router)
        self.assertEqual(
            router.count("ADImport.created_at.desc(), ADImport.id.desc()"),
            4,
        )

    def test_coverage_and_narrative_records_are_bounded_before_provider_use(self):
        coverage = (
            ROOT / "backend" / "app" / "gap_detection" / "service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("MAX_GAP_ANALYSIS_FINDINGS = 500", coverage)
        self.assertIn("MAX_GAP_ANALYSIS_CHECKLIST_ITEMS = 1_000", coverage)
        self.assertIn("select(func.count(model.id))", coverage)
        self.assertLess(coverage.index("count_limits = ("), coverage.index("get_provider()"))

        narrative = (
            ROOT / "backend" / "app" / "narrative" / "service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("MAX_NARRATIVE_FINDINGS = 500", narrative)
        self.assertIn("MAX_NARRATIVE_ATTACK_PATHS = 100", narrative)
        self.assertGreaterEqual(
            narrative.count(".limit(MAX_NARRATIVE_FINDINGS + 1)"),
            2,
        )
        self.assertGreaterEqual(
            narrative.count(".limit(MAX_NARRATIVE_ATTACK_PATHS + 1)"),
            2,
        )

        page = (ROOT / "frontend" / "src" / "pages" / "EngagementDetail.jsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("Delete the saved attack narrative?", page)
        self.assertIn("Could not copy the narrative to the clipboard", page)

        gap_router = (
            ROOT / "backend" / "app" / "gap_detection" / "router.py"
        ).read_text(encoding="utf-8")
        narrative_router = (
            ROOT / "backend" / "app" / "narrative" / "router.py"
        ).read_text(encoding="utf-8")
        self.assertIn("status_code=413", gap_router)
        self.assertGreaterEqual(narrative_router.count("status_code=413"), 2)

    def test_zero_cvss_is_not_treated_as_missing(self):
        for path in (ROOT / "backend" / "app").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("cvss_score or 'N/A'", source, path)
            self.assertNotIn('cvss_score or "N/A"', source, path)
            self.assertNotIn("if f.cvss_score else None", source, path)
            self.assertNotIn("if finding.cvss_score else None", source, path)
            self.assertNotIn("finding.cvss_score and (", source, path)
        engagement_page = (
            ROOT / "frontend" / "src" / "pages" / "EngagementDetail.jsx"
        ).read_text(encoding="utf-8")
        self.assertNotIn("finding.cvss_score || '-'", engagement_page)
        knowledge_page = (
            ROOT / "frontend" / "src" / "pages" / "KnowledgeBase.jsx"
        ).read_text(encoding="utf-8")
        self.assertNotIn("detail.entry.default_cvss &&", knowledge_page)

    def test_report_template_selection_matches_the_server_default(self):
        engagement_page = (
            ROOT / "frontend" / "src" / "pages" / "EngagementDetail.jsx"
        ).read_text(encoding="utf-8")

        self.assertNotIn(">Default Branding</option>", engagement_page)
        self.assertIn("setSelectedTemplate(defaultTemplate.id);", engagement_page)
        self.assertIn("Automatic: ${defaultTemplate.name}", engagement_page)
        self.assertIn('report.template_used ? ` with "${report.template_used}" template`', engagement_page)

    def test_advertised_bedrock_provider_is_installed_and_packaged(self):
        requirements = (ROOT / "backend" / "requirements.txt").read_text(
            encoding="utf-8"
        )
        specification = (ROOT / "breachwright.spec").read_text(encoding="utf-8")
        self.assertIn("boto3==", requirements)
        self.assertIn('"boto3", "botocore"', specification)
        excludes = specification.split("_excludes = [", 1)[1].split("]", 1)[0]
        self.assertNotIn('"boto3"', excludes)
        self.assertNotIn('"botocore"', excludes)

    def test_release_automation_has_zero_cost_compute_guardrails(self):
        workflows = {
            path.name: path.read_text(encoding="utf-8")
            for path in (ROOT / ".github" / "workflows").glob("*.yml")
        }
        self.assertEqual(
            {"candidate-build.yml", "ci.yml", "codeql.yml"},
            set(workflows),
        )
        for name, source in workflows.items():
            self.assertIn("cancel-in-progress: true", source, name)
            self.assertNotIn("self-hosted", source, name)
            if name != "candidate-build.yml":
                self.assertNotIn("actions/upload-artifact", source, name)

        candidate = workflows["candidate-build.yml"]
        self.assertIn("retain_release_artifacts:", candidate)
        self.assertIn(
            "github.event_name == 'workflow_dispatch' && inputs.retain_release_artifacts",
            candidate,
        )
        self.assertIn("uses: actions/upload-artifact@v6", candidate)
        self.assertIn("retention-days: 1", candidate)
        self.assertIn("timeout-minutes: 30", candidate)
        self.assertIn("timeout-minutes: 10", candidate)
        self.assertIn("Acquire::Retries=3", candidate)
        self.assertIn("ubuntu-latest", candidate)
        self.assertIn("windows-latest", candidate)


if __name__ == "__main__":
    unittest.main()
