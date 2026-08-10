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
