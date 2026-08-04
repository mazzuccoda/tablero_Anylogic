from django.contrib import admin

from .models import ImportBatch, ImportedFile, Project, Scenario, SimulationRun


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("nombre", "creado")


@admin.register(Scenario)
class ScenarioAdmin(admin.ModelAdmin):
    list_display = ("codigo", "project", "creado")


@admin.register(SimulationRun)
class SimulationRunAdmin(admin.ModelAdmin):
    list_display = ("run_id", "scenario", "tipo", "nivel_auditoria", "version_esquema", "importado")
    list_filter = ("tipo", "nivel_auditoria")
    search_fields = ("run_id",)


class ImportedFileInline(admin.TabularInline):
    model = ImportedFile
    extra = 0


@admin.register(ImportBatch)
class ImportBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "simulation_run", "estado", "version_esquema", "creado")
    list_filter = ("estado",)
    inlines = [ImportedFileInline]
