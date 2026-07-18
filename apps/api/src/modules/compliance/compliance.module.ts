import { Module } from "@nestjs/common";
import { ComplianceService } from "./compliance.service";
import { ComplianceController } from "./compliance.controller";
import { ContextBuilderService } from "../context-builder/context-builder.service";
import { CitationValidatorService } from "../citation-validator/citation-validator.service";
import { HybridRegulationSearchTool } from "./hybrid-regulation-search.tool";
import { RegulatoryAgentService } from "./regulatory-agent.service";
import { AgentRunLoggerService } from "./agent-run-logger.service";
import { WikiService } from "../wiki/wiki.service";

@Module({
  providers: [
    ComplianceService,
    RegulatoryAgentService,
    HybridRegulationSearchTool,
    ContextBuilderService,
    CitationValidatorService,
    AgentRunLoggerService,
    WikiService,
  ],
  controllers: [ComplianceController],
})
export class ComplianceModule {}
