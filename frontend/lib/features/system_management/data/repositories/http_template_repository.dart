import '../../../../core/constants/api_paths.dart';
import '../../../../core/network/api_client.dart';
import '../../../../shared/models/api_response.dart';
import '../models/task_template_models.dart';
import 'template_repository.dart';

class HttpTemplateRepository implements TemplateRepository {
  final ApiClient apiClient;

  const HttpTemplateRepository({
    required this.apiClient,
  });

  @override
  Future<List<TaskTemplateModel>> fetchTaskTemplates() async {
    final json = await apiClient.getJson(ApiPaths.taskTemplates);
    final response = ApiResponse<List<TaskTemplateModel>>.fromJson(
      json,
      (rawData) {
        final items = rawData as List<dynamic>? ?? [];
        return items
            .whereType<Map<String, dynamic>>()
            .map(TaskTemplateModel.fromJson)
            .toList();
      },
    );
    return response.data ?? const [];
  }

  @override
  Future<TaskTemplateModel> createTaskTemplate(
      TaskTemplateModel template) async {
    final json = await apiClient.postJson(
      ApiPaths.taskTemplates,
      body: template.toJson(),
    );
    final response = ApiResponse<TaskTemplateModel>.fromJson(
      json,
      (rawData) => TaskTemplateModel.fromJson(
        rawData as Map<String, dynamic>? ?? {},
      ),
    );
    return response.data ?? template;
  }

  @override
  Future<TaskTemplateModel> updateTaskTemplate(
      TaskTemplateModel template) async {
    final json = await apiClient.putJson(
      '${ApiPaths.taskTemplates}/${template.id}',
      body: template.toJson(),
    );
    final response = ApiResponse<TaskTemplateModel>.fromJson(
      json,
      (rawData) => TaskTemplateModel.fromJson(
        rawData as Map<String, dynamic>? ?? {},
      ),
    );
    return response.data ?? template;
  }

  @override
  Future<void> deleteTaskTemplate(String templateId) async {
    await apiClient.deleteJson('${ApiPaths.taskTemplates}/$templateId');
  }

  @override
  Future<TaskTemplateModel> trackTaskTemplateUse(String templateId) async {
    final json = await apiClient.postJson(ApiPaths.useTaskTemplate(templateId));
    final response = ApiResponse<TaskTemplateModel>.fromJson(
      json,
      (rawData) => TaskTemplateModel.fromJson(
        rawData as Map<String, dynamic>? ?? {},
      ),
    );
    return response.data ??
        const TaskTemplateModel(
          id: '',
          label: '',
          name: '',
          startUrl: '',
          cronExpr: '',
          parserRules: null,
          enabled: true,
          description: '',
          tags: [],
          usageCount: 0,
          lastUsedAt: null,
        );
  }

  @override
  Future<TestTemplateResponse> testTaskTemplate(
      TestTemplateRequest request) async {
    final json = await apiClient.postJson(
      ApiPaths.testTemplate,
      body: request.toJson(),
    );
    final response = ApiResponse<TestTemplateResponse>.fromJson(
      json,
      (rawData) => TestTemplateResponse.fromJson(
        rawData as Map<String, dynamic>? ?? {},
      ),
    );
    return response.data ?? const TestTemplateResponse();
  }

  @override
  Future<ManualCollectionResult> collectManualSource(
    String templateId,
    String url,
  ) async {
    final json = await apiClient.postJson(
      ApiPaths.collectManualSource(templateId),
      body: {'url': url},
    );
    final response = ApiResponse<ManualCollectionResult>.fromJson(
      json,
      (rawData) => ManualCollectionResult.fromJson(
        rawData as Map<String, dynamic>? ?? {},
      ),
    );
    return response.data ??
        ManualCollectionResult(
          sourceId: templateId,
          sourceUrl: url,
          status: '',
          noticeId: 0,
        );
  }
}
