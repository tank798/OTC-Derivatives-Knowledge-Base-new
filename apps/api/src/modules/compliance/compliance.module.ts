import { Module } from "@nestjs/common";
import { ComplianceService } from "./compliance.service";
import { ComplianceController } from "./compliance.controller";
import { ContextBuilderService } from "../context-builder/context-builder.service";
import { CitationValidatorService } from "../citation-validator/citation-validator.service";
import { AgentWorkflowService } from "./agent-workflow.service";
import { HybridRegulationSearchTool } from "./hybrid-regulation-search.tool";

@Module({
  providers: [ComplianceService, AgentWorkflowService, HybridRegulationSearchTool, ContextBuilderService, CitationValidatorService],
  controllers: [ComplianceController],
})
export class ComplianceModule {}
