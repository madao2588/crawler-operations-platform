import '../../../../core/constants/api_paths.dart';
import '../../../../core/network/api_client.dart';
import '../../../../shared/models/api_response.dart';
import '../../../../shared/models/page_data.dart';
import '../models/notice_models.dart';
import 'notice_repository.dart';

class HttpNoticeRepository implements NoticeRepository {
  final ApiClient apiClient;

  const HttpNoticeRepository({
    required this.apiClient,
  });

  @override
  Future<List<NoticeSourceSiteOption>> fetchSourceSites() async {
    final json = await apiClient.getJson(ApiPaths.noticeSourceSites);
    final response = ApiResponse<List<NoticeSourceSiteOption>>.fromJson(
      json,
      (rawData) {
        if (rawData is! List) {
          return const <NoticeSourceSiteOption>[];
        }
        return rawData
            .whereType<Map>()
            .map(
              (value) => NoticeSourceSiteOption.fromJson(
                Map<String, dynamic>.from(value),
              ),
            )
            .where(
              (option) =>
                  option.sourceSite.isNotEmpty && option.displayName.isNotEmpty,
            )
            .toList();
      },
    );
    return response.data ?? const <NoticeSourceSiteOption>[];
  }

  @override
  Future<PageData<NoticeListItemModel>> fetchNotices({
    int page = 1,
    int pageSize = 20,
    String? keyword,
    String? category,
    String? reviewStatus,
    bool? archived,
    bool? capturedToday,
    String? sourceSite,
    bool? keywordHit,
    bool? highPriority,
    bool? highQuality,
    String? projectSignal,
  }) async {
    final queryParameters = <String, String>{
      'page': '$page',
      'page_size': '$pageSize',
    };
    if (keyword != null && keyword.trim().isNotEmpty) {
      queryParameters['keyword'] = keyword.trim();
    }
    if (category != null && category.trim().isNotEmpty) {
      queryParameters['category'] = category.trim();
    }
    if (reviewStatus != null && reviewStatus.trim().isNotEmpty) {
      queryParameters['review_status'] = reviewStatus.trim();
    }
    if (archived != null) {
      queryParameters['archived'] = archived ? 'true' : 'false';
    }
    if (capturedToday != null) {
      queryParameters['captured_today'] = capturedToday ? 'true' : 'false';
    }
    if (sourceSite != null && sourceSite.trim().isNotEmpty) {
      queryParameters['source_site'] = sourceSite.trim();
    }
    if (keywordHit != null) {
      queryParameters['keyword_hit'] = keywordHit ? 'true' : 'false';
    }
    if (highPriority != null) {
      queryParameters['high_priority'] = highPriority ? 'true' : 'false';
    }
    if (highQuality != null) {
      queryParameters['high_quality'] = highQuality ? 'true' : 'false';
    }
    if (projectSignal != null && projectSignal.trim().isNotEmpty) {
      queryParameters['project_signal'] = projectSignal.trim();
    }
    final json = await apiClient.getJson(
      ApiPaths.notices,
      queryParameters: queryParameters,
    );

    final response = ApiResponse<PageData<NoticeListItemModel>>.fromJson(
      json,
      (rawData) => PageData<NoticeListItemModel>.fromJson(
        rawData as Map<String, dynamic>? ?? {},
        NoticeListItemModel.fromJson,
      ),
    );

    return response.data ??
        const PageData<NoticeListItemModel>(
          items: [],
          total: 0,
          page: 1,
          pageSize: 20,
        );
  }

  @override
  Future<NoticeDetailModel> fetchNoticeDetail(int id) async {
    final json = await apiClient.getJson(ApiPaths.noticeDetail(id));
    final response = ApiResponse<NoticeDetailModel>.fromJson(
      json,
      (rawData) => NoticeDetailModel.fromJson(
        rawData as Map<String, dynamic>? ?? {},
      ),
    );
    return response.data ?? _emptyDetail(id);
  }

  @override
  Future<NoticeDetailModel> updateNoticeReview(
    int id,
    NoticeReviewPayload payload,
  ) async {
    final json = await apiClient.patchJson(
      ApiPaths.noticeReview(id),
      body: payload.toJson(),
    );
    final response = ApiResponse<NoticeDetailModel>.fromJson(
      json,
      (rawData) => NoticeDetailModel.fromJson(
        rawData as Map<String, dynamic>? ?? {},
      ),
    );
    return response.data ?? _emptyDetail(id);
  }

  @override
  Future<List<int>> downloadCollectedDataExport({
    int limit = 5000,
    int? taskId,
    String? category,
    String? reviewStatus,
    bool? archived,
  }) async {
    final q = <String, String>{'limit': '$limit'};
    if (taskId != null) {
      q['task_id'] = '$taskId';
    }
    _addExportFilters(
      q,
      category: category,
      reviewStatus: reviewStatus,
      archived: archived,
    );
    return apiClient.getBytes(ApiPaths.dataExportCsv, queryParameters: q);
  }

  @override
  Future<List<int>> downloadInformationPoolExcel({
    int limit = 5000,
    int? taskId,
    String? category,
    String? reviewStatus,
    bool? archived,
  }) async {
    final q = <String, String>{'limit': '$limit'};
    if (taskId != null) {
      q['task_id'] = '$taskId';
    }
    _addExportFilters(
      q,
      category: category,
      reviewStatus: reviewStatus,
      archived: archived,
    );
    return apiClient.getBytes(ApiPaths.dataExportExcel, queryParameters: q);
  }

  void _addExportFilters(
    Map<String, String> queryParameters, {
    String? category,
    String? reviewStatus,
    bool? archived,
  }) {
    if (category != null && category.trim().isNotEmpty) {
      queryParameters['category'] = category.trim();
    }
    if (reviewStatus != null && reviewStatus.trim().isNotEmpty) {
      queryParameters['review_status'] = reviewStatus.trim();
    }
    if (archived != null) {
      queryParameters['archived'] = archived ? 'true' : 'false';
    }
  }

  @override
  Future<NoticeSnapshotModel> fetchSnapshot(int id) async {
    final json = await apiClient.getJson(ApiPaths.noticeSnapshot(id));
    final response = ApiResponse<NoticeSnapshotModel>.fromJson(
      json,
      (rawData) => NoticeSnapshotModel.fromJson(
        rawData as Map<String, dynamic>? ?? {},
      ),
    );
    return response.data ??
        const NoticeSnapshotModel(
          id: 0,
          sourceUrl: '',
          sourceSite: '',
          snapshotPath: '',
          content: '',
        );
  }

  NoticeDetailModel _emptyDetail(int id) {
    return NoticeDetailModel(
      id: id,
      title: '',
      summary: '',
      sourceSite: '',
      sourceUrl: '',
      publishedAt: null,
      capturedAt: '',
      qualityScore: 0,
      matchedKeywords: const [],
      isHighPriority: false,
      category: '未分类',
      aiSummary: null,
      reviewStatus: '待关注',
      isArchived: false,
      remark: null,
      taskId: 0,
      contentText: '',
      contentHtml: '',
      contentHash: null,
      snapshotPath: null,
      metadata: null,
    );
  }
}
