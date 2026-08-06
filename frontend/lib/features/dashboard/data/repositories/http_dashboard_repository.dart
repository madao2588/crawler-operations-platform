import '../../../../core/constants/api_paths.dart';
import '../../../../core/network/api_client.dart';
import '../../../../shared/models/api_response.dart';
import '../models/dashboard_models.dart';
import 'dashboard_repository.dart';

class HttpDashboardRepository implements DashboardRepository {
  final ApiClient apiClient;

  const HttpDashboardRepository({
    required this.apiClient,
  });

  @override
  Future<DashboardOverviewModel> fetchOverview() async {
    final json = await apiClient.getJson(ApiPaths.dashboardOverview);
    final response = ApiResponse<DashboardOverviewModel>.fromJson(
      json,
      (rawData) => DashboardOverviewModel.fromJson(
        rawData as Map<String, dynamic>? ?? {},
      ),
    );
    return response.data ?? _emptyOverview();
  }

  DashboardOverviewModel _emptyOverview() {
    return const DashboardOverviewModel(
      metrics: DashboardMetricsModel(
        todayNewNotices: 0,
        keywordHitNotices: 0,
        monitoringSiteCount: 0,
        highPriorityNotices: 0,
        projectDeclarationNotices: 0,
        resultPublicationNotices: 0,
      ),
      runtime: DashboardRuntimeModel(
        status: 'unknown',
        database: 'unknown',
        scheduler: 'unknown',
        scheduledJobs: 0,
      ),
      highValueNotices: [],
      recentNotices: [],
      keywordHeat: [],
      sourceDistribution: [],
      projectSignalDistribution: [],
      lastUpdatedAt: null,
    );
  }
}
