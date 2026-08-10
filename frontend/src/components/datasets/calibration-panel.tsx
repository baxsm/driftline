import type { FC } from "react";
import type { CameraCalibration, ImuCalibration } from "@/lib/types";

interface CalibrationPanelProps {
  cameras: CameraCalibration[];
  imu?: ImuCalibration;
}

const Row: FC<{ label: string; value: string; unit?: string }> = ({ label, value, unit }) => (
  <div className="flex items-baseline justify-between gap-4 py-1.5">
    <span className="text-muted-foreground text-xs">{label}</span>
    <span className="font-mono text-foreground text-xs">
      {value}
      {unit ? <span className="ml-1 text-muted-foreground">{unit}</span> : null}
    </span>
  </div>
);

const IMU_FIELDS: Array<{ key: keyof ImuCalibration; label: string; unit: string }> = [
  { key: "gyro_noise", label: "Gyro noise density", unit: "rad/s^0.5" },
  { key: "accel_noise", label: "Accel noise density", unit: "m/s^1.5" },
  { key: "gyro_bias_rw", label: "Gyro random walk", unit: "rad/s^1.5" },
  { key: "accel_bias_rw", label: "Accel random walk", unit: "m/s^2.5" },
  { key: "update_rate_hz", label: "Update rate", unit: "Hz" },
];

const CalibrationPanel: FC<CalibrationPanelProps> = ({ cameras, imu }) => (
  <div className="flex flex-col gap-6">
    {cameras.map((camera) => {
      const { name, camera_model, distortion_model, intrinsics, resolution } = camera;
      return (
        <section key={name} className="flex flex-col">
          <h3 className="mb-1 font-mono text-foreground text-xs uppercase tracking-wide">{name}</h3>
          <div className="divide-y divide-border border-border border-t">
            <Row label="Model" value={`${camera_model} / ${distortion_model}`} />
            <Row
              label="Resolution"
              value={`${resolution.width} x ${resolution.height}`}
              unit="px"
            />
            <Row label="fx" value={intrinsics.fx.toFixed(4)} unit="px" />
            <Row label="fy" value={intrinsics.fy.toFixed(4)} unit="px" />
            <Row label="cx" value={intrinsics.cx.toFixed(4)} unit="px" />
            <Row label="cy" value={intrinsics.cy.toFixed(4)} unit="px" />
          </div>
        </section>
      );
    })}

    {imu && Object.keys(imu).length > 0 ? (
      <section className="flex flex-col">
        <h3 className="mb-1 font-mono text-foreground text-xs uppercase tracking-wide">imu</h3>
        <div className="divide-y divide-border border-border border-t">
          {IMU_FIELDS.map(({ key, label, unit }) => {
            const value = imu[key];
            if (value == null) return null;
            return <Row key={key} label={label} value={String(value)} unit={unit} />;
          })}
        </div>
      </section>
    ) : null}
  </div>
);

export default CalibrationPanel;
