export type DatasetSource = "tum_vi" | "euroc" | "custom";

export interface DatasetSummary {
  id: string;
  name: string;
  source: DatasetSource;
  has_ground_truth: boolean;
  frame_count: number;
  imu_sample_count: number;
  duration_seconds: number;
  camera_model: string | null;
  created_at: string;
}

export interface CameraCalibration {
  name: string;
  camera_model: string;
  distortion_model: string;
  distortion_coeffs: number[];
  intrinsics: { fx: number; fy: number; cx: number; cy: number };
  resolution: { width: number; height: number };
  t_cam_imu: number[][] | null;
  t_cn_cnm1: number[][] | null;
}

export interface ImuCalibration {
  gyro_noise?: number;
  accel_noise?: number;
  gyro_bias_rw?: number;
  accel_bias_rw?: number;
  update_rate_hz?: number;
}

export interface Dataset extends DatasetSummary {
  path: string;
  calibration: { cameras?: CameraCalibration[]; imu?: ImuCalibration };
}

/**
 * Timestamps arrive as strings because a 19 digit nanosecond value does not survive
 * JSON.parse into a JavaScript number.
 */
export interface Pose {
  timestamp_ns: string;
  tx: number;
  ty: number;
  tz: number;
  qw: number;
  qx: number;
  qy: number;
  qz: number;
}

export interface GroundTruthResponse {
  poses: Pose[];
  stride: number;
  /** Total truth poses before decimation, so the UI can say "N of M drawn". */
  total: number;
  has_ground_truth: boolean;
}

export interface User {
  id: string;
  email: string;
}

export type RunStatus = "queued" | "running" | "done" | "failed";

/**
 * Only the fields phase 2 actually estimates. Keyframe, window, and IMU settings arrive with
 * the stages that use them, because a control that changes nothing is worse than no control.
 */
export type EstimatorMode = "mono" | "mono_inertial";

export interface EstimatorConfig {
  mode: EstimatorMode;
  max_features: number;
  corner_quality: number;
  min_feature_distance_px: number;
  ransac_threshold_px: number;
  redetect_below: number;
  min_track_length: number;
  max_frames: number | null;
  start_frame: number;
  enhance_contrast: boolean;
  keyframe_parallax_px: number;
  max_frames_without_keyframe: number;
}

export interface RunSummary {
  id: string;
  dataset_id: string;
  dataset_name: string | null;
  label: string | null;
  config_hash: string;
  status: RunStatus;
  failure_reason: string | null;
  processed_frames: number;
  total_frames: number;
  created_at: string;
  finished_at: string | null;
  /** Null on a run that was never scored. Never zero, which would rank as the best run. */
  ate_rmse: number | null;
  /** How that ATE was fitted. Two ATEs aligned differently are not the same measurement. */
  alignment: AlignmentMode | null;
}

/** Server side, because the list is paginated and sorting one page is not sorting the list. */
export type RunSort = "created" | "ate" | "dataset";

export interface Run {
  id: string;
  dataset_id: string;
  label: string | null;
  config: EstimatorConfig;
  config_hash: string;
  status: RunStatus;
  failure_reason: string | null;
  failure_frame: number | null;
  processed_frames: number;
  total_frames: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

/** An estimated pose carries what the front end tracked into that frame. */
export interface EstimatedPose extends Pose {
  frame_index: number;
  tracked_features: number | null;
}

export interface TrajectoryResponse {
  poses: EstimatedPose[];
  stride: number;
  total: number;
  /** Monocular translation has no absolute scale, so the viewer must not label it in metres. */
  scale_is_arbitrary: boolean;
  /** Whether these poses were mapped onto the ground truth frame. */
  aligned: boolean;
  alignment?: AlignmentMode;
}

/**
 * How the estimate was fitted onto truth before measuring. Never hidden from the reader: an
 * ATE without it is not comparable, and Sim(3) on a run that observes scale hides scale
 * drift completely.
 */
export type AlignmentMode = "se3" | "sim3";

export interface RunMetrics {
  ate_rmse: number;
  ate_mean: number;
  ate_median: number;
  ate_max: number;
  ate_rot_rmse: number;
  ate_rot_std: number;
  rpe_trans_rmse: number | null;
  rpe_rot_rmse: number | null;
  rpe_delta_frames: number;
  /** The Sim(3) factor, null for SE(3) where scale was never solved for. */
  scale_error: number | null;
  alignment: AlignmentMode;
  aligned_pose_count: number;
  candidate_pose_count: number;
  association_tolerance_ns: string;
  computed_at: string;
}

export interface MetricsResponse {
  /** Null when the run was not scored. Never zeros, which would read as a perfect estimate. */
  metrics: RunMetrics | null;
  has_ground_truth: boolean;
  status: RunStatus;
}

export interface PoseErrorPoint {
  timestamp_ns: string;
  trans_error: number;
  rot_error: number;
}

export interface PoseErrorsResponse {
  errors: PoseErrorPoint[];
  stride: number;
  total: number;
}

export interface TrackedFeature {
  id: number;
  x: number;
  y: number;
  age: number;
}

export interface TrackFrame {
  frame_index: number;
  timestamp_ns: string;
  features: TrackedFeature[];
}

export interface TracksResponse {
  frames: TrackFrame[];
}

export interface RunProgress {
  frame: number;
  total: number;
  status: RunStatus;
  failure_reason: string | null;
  failure_frame: number | null;
}

/**
 * One config key that differs between two runs. Keys that match are not sent: the reason to
 * open compare is to find what changed, and fifteen identical rows bury it.
 */
export interface ConfigDiffRow {
  key: string;
  a: unknown;
  b: unknown;
}

/**
 * One metric across both runs.
 *
 * `delta` is null rather than zero whenever subtracting the two sides would be meaningless:
 * a metric missing on one side, or two runs aligned differently. `comparable` says which of
 * those it was, so the UI can explain the gap instead of just leaving it blank.
 */
export interface MetricDeltaRow {
  key: string;
  a: number | null;
  b: number | null;
  delta: number | null;
  comparable: boolean;
}

/** An error sample on the elapsed-seconds axis the two runs share. */
export interface CompareErrorPoint {
  t: number;
  trans_error: number;
  rot_error: number;
}

export interface CompareSide {
  id: string;
  label: string | null;
  dataset_id: string;
  dataset_name: string | null;
  config: EstimatorConfig;
  config_hash: string;
  status: RunStatus;
  failure_reason: string | null;
  failure_frame: number | null;
  processed_frames: number;
  total_frames: number;
  created_at: string;
  metrics: RunMetrics | null;
  errors: CompareErrorPoint[];
}

export interface CompareResponse {
  a: CompareSide;
  b: CompareSide;
  config_diff: ConfigDiffRow[];
  metric_deltas: MetricDeltaRow[];
  /** Both runs are on this sequence, so one ground truth path serves the shared viewer. */
  dataset_id: string;
}
