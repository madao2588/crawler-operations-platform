import '../models/task_template_models.dart';

abstract class TemplateRepository {
  Future<List<TaskTemplateModel>> fetchTaskTemplates();

  Future<TaskTemplateModel> createTaskTemplate(TaskTemplateModel template);

  Future<TaskTemplateModel> updateTaskTemplate(TaskTemplateModel template);

  Future<void> deleteTaskTemplate(String templateId);

  Future<TaskTemplateModel> trackTaskTemplateUse(String templateId);

  Future<TestTemplateResponse> testTaskTemplate(TestTemplateRequest request);

  Future<ManualCollectionResult> collectManualSource(
    String templateId,
    String url,
  );
}
