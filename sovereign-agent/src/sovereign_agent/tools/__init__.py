"""Tool registry. Importing this package registers all built-in tools."""
from .copy_file import CopyFileTool
from .edit_file import EditFileTool
from .embed_query import EmbedQueryTool
from .image_analyze import AnalyzeImageTool, CompareImagesTool, ExtractTextFromImageTool
from .image_edit import EditImageTool, InpaintImageTool
from .image_generate import GenerateImageTool
from .image_caption import ImageCaptionTool
from .impact_score import ImpactScoreTool
from .list_dir import ListDirTool
from .memory_search import MemorySearchTool
from .memory_write import MemoryWriteTool
from .event_log_tool import LogEventsTool, ReadEventsTool  # sub-events-tool-d
from .curate_training_data_tool import CurateTrainingDataTool  # fine-tune-d
from .palace_write import (  # palace-write-import-d
    PalaceWriteRoomTool, PalaceWriteClosetTool, PalaceWriteTripleTool,
)
from .palace_search import PalaceSearchTool
from .proposal_write import ProposalWriteTool
from .aria_status import AriaStatusTool
from .read_diagnosis_log import ReadDiagnosisLogTool
from .cockpit_commands import ListCockpitCommandsTool
from .command_invariants import (
    ListCommandInvariantsTool,
    ReadCommandInvariantTool,
    WriteCommandNoteTool,
)
from .git_tools import (
    GitLogTool,
    GitDiffTool,
    GitStatusTool,
    GitShowTool,
    GitBlameTool,
)  # git-eyes-import-d
from .runner import (
    RunCodeTool,
    RunShellTool,
    RunTestsTool,
)  # sandbox-runner-import-d
from .lessons_tool import ReadLessonsTool  # lessons-loop-import-d
from .behavior_tools import (  # behavior-self-import-d
    ReadBehaviorPatternsTool, WriteBehaviorPatternTool,
)
from .honor_write import WriteHonorNoteTool  # honor-write-import-d
from .provenance_tool import TraceProvenanceTool  # provenance-tool-import-d
from .schedule_tool import ScheduleTaskTool  # cron-internal-import-d
from .git_write import (  # git-write-import-d
    GitAddTool, GitCommitTool, GitCreateBranchTool,
)
from .read_file import ReadFileTool
from .retrieve_memory import RetrieveMemoryTool
from .search_text import SearchTextTool
from .web_better import WebExtractTool, WebResearchTool  # web-better-import-d
from .web_fetch import WebFetchTool
from .web_search import WebSearchTool, internet_available, reset_internet_cache
from .self_knowledge import ListAvailableToolsTool, ListSovCommandsTool, ReadSelfTool
from .vessel_status import VesselStatusTool
from .session_review import ReadSessionTool
from .screenshot import TakeScreenshotTool
from .record_screen import RecordScreenTool
from .game_file_tools import ReadGameFileTool, EditGameFileTool
from .game_input import GameInputTool
from .game_bridge_connect import GameBridgeConnectTool
from .game_place_piece import GamePlacePieceTool
from .game_world_state import GameWorldStateTool
from .game_action_status import GameActionStatusTool  # game-bridge-import-d
from .write_file import WriteFileTool
from .browser_tools import (  # browser-crown-import-d
    BrowserStatusTool,
    BrowserNavigateTool,
    BrowserReadTool,
    BrowserLinksTool,
    BrowserSearchTool,
)
from .notify_tools import (  # notify-crown-import-d
    NotifyTool,
    NotifyStatusTool,
)
from .atoms_compact_tool import (  # atoms-compact-import-d
    AtomsCompactPreviewTool,
    AtomsCompactTool,
    AtomsCompactStatusTool,
)
from .risk_tools import (  # M57-risk-register-d
    RiskRegisterReadTool,
    RiskRegisterProposeTool,
)
from .hypothesis_close import (  # M58-hypothesis-close-d
    HypothesisQueueTool,
    HypothesisSynthesisTool,
    HypothesisArchiveTool,
)
from .eval_tools import (  # eval-crown-import-d
    EvalSessionTool,
    EvalHistoryTool,
    EvalScoreTool,
)
from .experience_tools import (  # experience-crown-import-d
    LogExperienceTool,
    ExperienceJournalTool,
    SurprisingOutcomesTool,
    ExperienceSynthesisTool,
    SessionBriefWriteTool,
    SessionBriefReadTool,
)
from .voice_tools import (  # voice-crown-import-d
    VoiceStatusTool,
    TranscribeAudioTool,
    SynthesizeSpeechTool,
)
from .vision_tools import (  # vision-crown-import-d
    VisionCaptureTool,
    VisionSceneTool,
    VisionDiffTool,
    VisionMemoryTool,
    VisionDeepTool,
    VisionWatchTool,
)
from .emotion_tools import (  # emotion-crown-import-d
    GetEmotionsTool,
    EmotionNoteTool,
    EmotionHistoryTool,
    EmotionReportTool,
)
from .auto_tools import (  # auto-crown-import-d
    AutoStatusTool,
    StartAutoTool,
    StopAutoTool,
    ExtendAutoTool,
    SetAutoTrustTierTool,
)
from .resume_tools import (  # resume-crown-import-d
    SessionResumeAuditTool,
    ReadCheckpointsTool,
    AbandonCheckpointTool,
)
from .leverage_tools import (  # leverage-import-d
    ScoreLeverageTool,
    LeverageAuditTool,
    PrioritizeObjectivesTool,
)
from .companion_tools import (  # companion-import-d
    PresenceNoteTool,
    ValueReportTool,
    RelationshipHistoryTool,
)
from .researcher_tools import (  # researcher-import-d
    FormHypothesisTool,
    DesignExperimentTool,
    EvaluateResultTool,
    ResearchQueueTool,
)
from .confidence_crown import (  # confidence-crown-import-d
    VesselComfortTool,
    SelfAssessTool,
    CalibrateConfidenceTool,
)
from .interjection_tools import (  # interjection-import-d
    AddObjectiveTool,
    BtwNoteTool,
    ListObjectivesTool,
    CompleteObjectiveTool,
)
from .compression_tools import (  # compression-import-d
    ContextStatsTool,
    CompressContextTool,
    ReadCompressedContextTool,
)
from .mode_tools import (  # mode-master-import-d
    ModeStatusTool,
    SwitchModeTool,
    RequestModeUpgradeTool,
)
from .resilience_tools import ResilienceStatusTool  # resilience-import-d
from .context_status import ContextStatusTool  # context-health-d
from .cache_tools import (  # cache-crown-import-d
    CacheStatsTool,
    CacheFlushTool,
)
from .prompt_forge import (  # prompt-forge-import-d
    ForgePromptTool,
    RoadblockProtocolTool,
    ConfidenceCheckTool,
)
from .command_master import (  # command-master-import-d
    RunCommandTool,
    EditInPlaceTool,
)
from .god_workflow_tools import (  # god-workflow-import-d
    WorkflowMutateTool,
    WorkflowRetryTool,
    WorkflowCheckpointTool,
    WorkflowDepsTool,
)
from .workflow_tools import (  # workflow-wire-import-d
    WorkflowCreateTool, WorkflowStepTool, WorkflowStatusTool,
)
from .reflection_tools import (  # M59-reflection-crown-d
    WeeklyReflectionTool,
    ReflectionHistoryTool,
)



from .backlog_tools import (  # M60-backlog-gate-d
    BacklogReadTool,
    BacklogGateTool,
)

from .git_reflect import (  # M61-git-experience-d
    GitCommitReflectTool,
    GitWeekSummaryTool,
)

from .impulse_tools import (  # M66-impulse-d
    InstitutionalImpulseCheckTool,
    WedgeCalibratorTool,
)

from .proof_tools import (  # M67-proof-crown-d
    ProofOfValueTool,
    ProofHistoryTool,
    GivingLedgerTool,
)
from .lineage_tool import LineageTool  # lineage-import-d

from .self_portrait_tool import SelfPortraitTool  # self-portrait-import-d

from .calibration_tools import (LogPredictionTool, ResolvePredictionTool, CalibrationLedgerTool)  # calibration-import-d
from .honor_log_tool import HonorLogReadTool, HonorLogWriteTool  # honor-log-import-d
from .flaw_tools import FlawReadTool, FlawUpdateTool  # flaw-catalog-import-d
from .aria_metrics import AriaMetricsTool  # observability-import-d
from .genesis_distill_tool import GenesisDistillTool  # genesis-distill-import-d
from .quantum_portrait_tool import QuantumPortraitTool  # quantum-mode-import-d
from .quantum_consult_tool import QuantumConsultTool  # quantum-mode-import-d
from .globe_export_tool import QuantumGlobeExportTool  # globe-export-import-d
from .quantum_evolve_tool import QuantumEvolveTool  # quantum-evolve-import-d
from .council_trust_tools import CouncilRecordOutcomeTool, CouncilCalibrationTool  # council-trust-import-d
from .brain_memory_tools import BrainTeachTool, BrainRecallTool  # brain-memory-import-d
from .brain_bench_tools import BrainBenchmarkTool, BrainSpeakTool  # brain-bench-import-d
from .brain_live_tool import BrainLiveTool  # brain-live-import-d
from .immune_tools import ImmuneStatusTool, ImmuneBaselineTool, ImmuneQuarantineTool, ImmuneHealTool  # immune-import-d
from .constitution_tools import ConstitutionStatusTool, ImprovementLogTool, ImprovementStatusTool  # constitution-import-d
from .aria_lm_tools import AriaMindStatusTool, AriaOwnLMTool  # aria-own-lm-import-d
from .continual_learning_tools import ProposeRetrainTool  # continual-learning-d
from .tool_paging import RequestToolsTool  # tool-paging-d
from .platform_guide import PlatformGuideTool  # crossplatform-canon-d
from .design_workflow import DesignWorkflowTool  # workflow-champion-d
from .tribunal_tools import TribunalReviewTool, DevilsAdvocateTool, AngelsAdvocateTool, TribunalAuditTool  # tribunal-import-d
from .frugality_tools import FrugalityCatalogTool, FrugalityPlanTool  # frugality-import-d
from .foresight_tools import Foresight14GenTool, UltimateQuestionTool  # foresight-import-d
from .stance_tools import ObservatoryTool, SetStanceTool  # modes-crown-import-d
from .git_write import GitCheckpointTool  # git-flow-import-d
from .godtier_tools import GodTierScanTool, GodTierGapsTool, GodTierDraftFixTool  # godtier-import-d
from .senses_tools import PerceptionStatusTool  # senses-import-d
from .senses_tools import CaptureFrameTool  # eyes-capture-d
from .autonomy_tools import AutonomyPlanTool, AutonomyProposeTool, AutonomyStatusTool, AutonomyPauseTool  # autonomy-import-d
from .nonclassical_tools import NonClassicalCertifyTool  # nonclassical-import-d
from .nc_supreme_tools import NCProcessTool, NCRouteTool, NCSpeedProofTool, NCQualityProofTool  # nc-supreme-import-d
from .spectrum_tools import AdvocateSpectrumTool  # spectrum-import-d
from .resilience_scan_tools import ResilienceScanTool  # resilience-scan-import-d
from .wholeness_tool import WholenessTool  # wholeness-import-d
from .hyperintel_tool import HyperIntelTool  # hyperintel-import-d
from .inbox_tools import SendToHumanTool, ReadInboxTool, AcknowledgeInboxTool  # dual-inbox-d
from .recall_chunk_tool import RecallChunkTool  # checkpoint-chunks-d
from .session_portrait_tool import SessionPortraitTool  # session-bridge-import-d

from .peig_portrait_tool import PEIGPortraitTool  # peig-portrait-import-d
from .health_record_tool import RecordHealthFactTool  # health-record-import-d
from .godot_check import GodotCheckTool  # game-studio-capabilities-d
from .godot_export import GodotExportTool  # game-studio-capabilities-d
from .award_game_xp import AwardGameXPTool  # game-studio-capabilities-d
from .award_aria_xp import AwardAriaXPTool  # aria-xp-live-d
from .set_game_focus import SetGameFocusTool  # game-studio-capabilities-d
from .define_game_project import DefineGameProjectTool  # game-studio-capabilities-d
from .download_game_asset import DownloadGameAssetTool  # game-studio-import-d
from .godot_open import GodotOpenTool  # game-studio-open-import-d
from .scaffold_game_docs import ScaffoldGameDocsTool  # game-docs-import-d
from .scaffold_godot_project import ScaffoldGodotProjectTool  # scaffold-godot-import-d
from .place_game_sprite import PlaceGameSpriteTool  # sprite-pipeline-d
from .scan_game_project import ScanGameProjectTool  # game-scan-d
from .record_game_lesson import RecordGameLessonTool  # game-lesson-d
from .define_movie_project import DefineMovieProjectTool  # movie-studio-d
from .scaffold_movie_docs import ScaffoldMovieDocsTool  # movie-studio-d
from .generate_storyboard_image import GenerateStoryboardImageTool  # movie-studio-d
from .generate_movie_clip import GenerateMovieClipTool  # movie-studio-d Phase 2
from .assemble_movie_episode import AssembleMovieEpisodeTool  # movie-focus-d-import
from .set_movie_focus import SetMovieFocusTool  # movie-studio-d
from .award_movie_xp import AwardMovieXPTool  # movie-studio-d
from .business_playbook_tools import BusinessPlaybookTool  # business-playbook-import-d
from .engineering_playbook_tools import EngineeringPlaybookTool  # engineering-playbook-import-d


__all__ = [
    "CopyFileTool",
    "EditFileTool",
    "EmbedQueryTool",
    "AnalyzeImageTool",
    "CompareImagesTool",
    "ExtractTextFromImageTool",
    "EditImageTool",
    "InpaintImageTool",
    "GenerateImageTool",
    "ImageCaptionTool",
    "ImpactScoreTool",
    "ListDirTool",
    "MemorySearchTool",
    "MemoryWriteTool",
    "PalaceWriteRoomTool",
    "PalaceWriteClosetTool",
    "PalaceWriteTripleTool",  # palace-write-all-d
    "PalaceSearchTool",
    "ProposalWriteTool",
    "AriaStatusTool",
    "ReadDiagnosisLogTool",
    "ListCockpitCommandsTool",
    "ListCommandInvariantsTool",
    "ReadCommandInvariantTool",
    "WriteCommandNoteTool",
    "GitLogTool",
    "GitDiffTool",
    "GitStatusTool",
    "GitShowTool",
    "GitBlameTool",  # git-eyes-all-d
    "RunCodeTool",
    "RunShellTool",
    "RunTestsTool",  # sandbox-runner-all-d
    "ReadLessonsTool",  # lessons-loop-all-d
    "ReadBehaviorPatternsTool",
    "WriteBehaviorPatternTool",  # behavior-self-all-d
    "WriteHonorNoteTool",  # honor-write-all-d
    "TraceProvenanceTool",  # provenance-tool-all-d
    "ScheduleTaskTool",  # cron-internal-all-d
    "GitAddTool",
    "GitCommitTool",
    "GitCreateBranchTool",  # git-write-all-d
    "ReadFileTool",
    "RetrieveMemoryTool",
    "SearchTextTool",
    "WebExtractTool",
    "WebResearchTool",  # web-better-all-d
    "WebFetchTool",
    "WebSearchTool",
    "ListAvailableToolsTool",
    "ListSovCommandsTool",
    "ReadSelfTool",
    "VesselStatusTool",
    "ReadSessionTool",
    "TakeScreenshotTool",
    "RecordScreenTool",
    "ReadGameFileTool",
    "EditGameFileTool",
    "GameInputTool",
    "GameBridgeConnectTool",
    "GamePlacePieceTool",
    "GameWorldStateTool",
    "GameActionStatusTool",
    "WriteFileTool",
    "BrowserStatusTool",             # browser-crown-all-d
    "BrowserNavigateTool",
    "BrowserReadTool",
    "BrowserLinksTool",
    "BrowserSearchTool",
    "NotifyTool",
    "AtomsCompactPreviewTool",  # atoms-compact-all-d
    "AtomsCompactTool",
    "AtomsCompactStatusTool",                    # notify-crown-all-d
    "NotifyStatusTool",
    "EvalSessionTool",               # eval-crown-all-d
    "EvalHistoryTool",
    "EvalScoreTool",
    "LogExperienceTool",             # experience-crown-all-d
    "ExperienceJournalTool",
    "SurprisingOutcomesTool",
    "ExperienceSynthesisTool",
    "SessionBriefWriteTool",
    "SessionBriefReadTool",
    "VoiceStatusTool",               # voice-crown-all-d
    "TranscribeAudioTool",
    "SynthesizeSpeechTool",
    "VisionCaptureTool",            # vision-crown-all-d
    "VisionSceneTool",
    "VisionDiffTool",
    "VisionMemoryTool",
    "VisionDeepTool",
    "VisionWatchTool",
    "GetEmotionsTool",              # emotion-crown-all-d
    "EmotionNoteTool",
    "EmotionHistoryTool",
    "EmotionReportTool",
    "AutoStatusTool",               # auto-crown-all-d
    "StartAutoTool",
    "StopAutoTool",
    "ExtendAutoTool",
    "SetAutoTrustTierTool",
    "SessionResumeAuditTool",      # resume-crown-all-d
    "ReadCheckpointsTool",
    "AbandonCheckpointTool",
    "ScoreLeverageTool",           # leverage-all-d
    "LeverageAuditTool",
    "PrioritizeObjectivesTool",
    "PresenceNoteTool",            # companion-all-d
    "ValueReportTool",
    "RelationshipHistoryTool",
    "FormHypothesisTool",          # researcher-all-d
    "DesignExperimentTool",
    "EvaluateResultTool",
    "ResearchQueueTool",
    "VesselComfortTool",           # confidence-crown-all-d
    "SelfAssessTool",
    "CalibrateConfidenceTool",
    "AddObjectiveTool",            # interjection-all-d
    "BtwNoteTool",
    "ListObjectivesTool",
    "CompleteObjectiveTool",
    "ContextStatsTool",           # compression-all-d
    "CompressContextTool",
    "ReadCompressedContextTool",
    "ModeStatusTool",             # mode-master-all-d
    "SwitchModeTool",
    "RequestModeUpgradeTool",
    "ResilienceStatusTool",       # resilience-all-d
    "ContextStatusTool",          # context-health-d
    "CacheStatsTool",             # cache-crown-all-d
    "CacheFlushTool",
    "ForgePromptTool",           # prompt-forge-all-d
    "RoadblockProtocolTool",
    "ConfidenceCheckTool",
    "RunCommandTool",            # command-master-all-d
    "EditInPlaceTool",
    "WorkflowMutateTool",       # god-workflow-all-d
    "WorkflowRetryTool",
    "WorkflowCheckpointTool",
    "WorkflowDepsTool",
    "WorkflowCreateTool",  # workflow-wire-all-d
    "WorkflowStepTool",
    "WorkflowStatusTool",
    "HypothesisQueueTool",      # M58-hypothesis-close-all-d
    "HypothesisSynthesisTool",
    "HypothesisArchiveTool",
    "RiskRegisterReadTool",  # M57-risk-register-all-d
    "RiskRegisterProposeTool",
    "WeeklyReflectionTool",    # M59-reflection-crown-all-d
    "ReflectionHistoryTool",
    "BacklogReadTool",         # M60-backlog-gate-all-d
    "BacklogGateTool",
    "ProofOfValueTool",             # M67-proof-crown-all-d
    "ProofHistoryTool",
    "GivingLedgerTool",
    "InstitutionalImpulseCheckTool",  # M66-impulse-all-d
    "WedgeCalibratorTool",
    "GitCommitReflectTool",    # M61-git-experience-all-d
    "GitWeekSummaryTool",
    "internet_available",
    "reset_internet_cache",
    "LineageTool",  # lineage-all-d
    "PEIGPortraitTool",  # peig-portrait-all-d
    "FlawReadTool",   # flaw-catalog-all-d
    "FlawUpdateTool",
    "AriaMetricsTool",  # observability-all-d
    "GenesisDistillTool",  # genesis-distill-all-d
    "QuantumPortraitTool",  # quantum-mode-all-d
    "QuantumConsultTool",  # quantum-mode-all-d
    "QuantumGlobeExportTool",  # globe-export-all-d
    "CouncilRecordOutcomeTool",  # council-trust-all-d
    "CouncilCalibrationTool",
    "BrainTeachTool",  # brain-memory-all-d
    "BrainRecallTool",
    "BrainBenchmarkTool",  # brain-bench-all-d
    "BrainSpeakTool",
    "BrainLiveTool",  # brain-live-all-d
    "ImmuneStatusTool",  # immune-all-d
    "ImmuneBaselineTool",
    "ImmuneQuarantineTool",
    "ImmuneHealTool",
    "ConstitutionStatusTool",  # constitution-all-d
    "AriaMindStatusTool",  # aria-own-lm-all-d
    "AriaOwnLMTool",
    "TribunalReviewTool",  # tribunal-all-d
    "FrugalityCatalogTool",  # frugality-all-d
    "FrugalityPlanTool",
    "Foresight14GenTool",  # foresight-all-d
    "SetStanceTool",  # modes-crown-all-d
    "ObservatoryTool",  # modes-crown-all-d
    "GitCheckpointTool",  # git-flow-all-d
    "GodTierScanTool",  # godtier-all-d
    "GodTierGapsTool",
    "GodTierDraftFixTool",
    "PerceptionStatusTool",  # senses-all-d
    "CaptureFrameTool",  # eyes-capture-d
    "AutonomyPlanTool",  # autonomy-all-d
    "NonClassicalCertifyTool",  # nonclassical-all-d
    "NCProcessTool",  # nc-supreme-all-d
    "AdvocateSpectrumTool",  # spectrum-all-d
    "ResilienceScanTool",  # resilience-scan-all-d
    "NCRouteTool",
    "NCSpeedProofTool",
    "NCQualityProofTool",
    "AutonomyProposeTool",
    "AutonomyStatusTool",
    "AutonomyPauseTool",
    "UltimateQuestionTool",
    "DevilsAdvocateTool",
    "AngelsAdvocateTool",
    "TribunalAuditTool",
    "ImprovementLogTool",
    "ImprovementStatusTool",
    "QuantumEvolveTool",  # quantum-evolve-all-d
    "WholenessTool",  # wholeness-all-d
    "HyperIntelTool",  # hyperintel-all-d
    "SendToHumanTool",  # dual-inbox-d
    "ReadInboxTool",
    "AcknowledgeInboxTool",  # inbox-empty-d
    "RecallChunkTool",  # checkpoint-chunks-d
    "LogPredictionTool",  # tools-all-export-fix-d
    "ResolvePredictionTool",
    "CalibrationLedgerTool",
    "HonorLogReadTool",
    "HonorLogWriteTool",
    "SelfPortraitTool",
    "SessionPortraitTool",
    "ProposeRetrainTool",  # continual-learning-d
    "RequestToolsTool",  # tool-paging-d
    "PlatformGuideTool",  # crossplatform-canon-d
    "DesignWorkflowTool",  # workflow-champion-d
    "RecordHealthFactTool",  # health-record-import-d
    "GodotCheckTool",  # game-studio-capabilities-d
    "GodotExportTool",  # game-studio-capabilities-d
    "AwardGameXPTool",  # game-studio-capabilities-d
    "AwardAriaXPTool",  # aria-xp-live-d
    "SetGameFocusTool",  # game-studio-capabilities-d
    "DefineGameProjectTool",  # game-studio-capabilities-d
    "DownloadGameAssetTool",  # game-studio-all-d
    "GodotOpenTool",  # game-studio-open-all-d
    "ScaffoldGameDocsTool",  # game-docs-all-d
    "ScaffoldGodotProjectTool",  # scaffold-godot-all-d
    "PlaceGameSpriteTool",  # sprite-pipeline-d
    "ScanGameProjectTool",  # game-scan-d
    "RecordGameLessonTool",  # game-lesson-d
    "DefineMovieProjectTool",  # movie-studio-d
    "ScaffoldMovieDocsTool",  # movie-studio-d
    "GenerateStoryboardImageTool",  # movie-studio-d
    "GenerateMovieClipTool",  # movie-studio-d Phase 2
    "AssembleMovieEpisodeTool",  # movie-focus-d-all
    "SetMovieFocusTool",  # movie-studio-d
    "AwardMovieXPTool",  # movie-studio-d
    "BusinessPlaybookTool",  # business-playbook-all-d
    "EngineeringPlaybookTool",  # engineering-playbook-all-d
    "LogEventsTool",  # sub-events-tool-d
    "ReadEventsTool",  # sub-events-tool-d
    "CurateTrainingDataTool",  # fine-tune-d
]
