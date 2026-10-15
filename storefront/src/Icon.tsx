import type { SVGProps } from "react";

const paths = {
  search: "m21 21-4.5-4.5M19 10.5a8.5 8.5 0 1 1-17 0 8.5 8.5 0 0 1 17 0Z",
  arrow: "M4 12h16m-6-6 6 6-6 6",
  external:
    "M14 3h7v7m0-7L10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5",
  chevron: "m9 5 7 7-7 7",
  close: "m6 6 12 12M6 18 18 6",
  check: "m5 12 4 4L19 6",
  tag: "M20 13 11 22 2 13V3h10l8 8a1.4 1.4 0 0 1 0 2ZM7 8h.01",
  bag: "M5 7h14l2 14H3L5 7Zm3 0V5a4 4 0 0 1 8 0v2",
  grid: "M3 3h7v7H3V3Zm11 0h7v7h-7V3ZM3 14h7v7H3v-7Zm11 0h7v7h-7v-7Z",
  phone:
    "M7 2h10a2 2 0 0 1 2 2v16a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Zm3 3h4m-3 14h2",
  home: "m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1V10Z",
  shirt: "m8 3-6 4 3 5 3-2v11h8V10l3 2 3-5-6-4a4 4 0 0 1-8 0Z",
  beauty: "M9 9h6v12H9V9Zm1 0V4l4-2v7M7 21h10",
  game: "M7 7h10c3 0 4 3 5 10 .5 4-3 5-5 1l-1-2H8l-1 2c-2 4-5.5 3-5-1 1-7 2-10 5-10Zm0 3v4m-2-2h4m7-1h.01M19 13h.01",
  shield: "m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6l9-4Zm-4 10 3 3 5-6",
  clock: "M12 8v5l3 2m7-3a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  filter: "M4 7h9m4 0h3M4 17h3m4 0h9M13 4v6M7 14v6",
  copy: "M9 9h12v12H9V9ZM5 15H3V3h12v2",
  info: "M12 11v6m0-10h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z",
  refresh: "M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 14 6M4 12a8 8 0 0 0 14 6",
  spark: "m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3 3-7Z",
} as const;

export type IconName = keyof typeof paths;

export default function Icon({
  name,
  size = 20,
  ...props
}: SVGProps<SVGSVGElement> & { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d={paths[name]} />
    </svg>
  );
}

export const categoryIcons: Record<string, IconName> = {
  "": "grid",
  eletronicos: "phone",
  casa: "home",
  moda: "shirt",
  beleza: "beauty",
  games: "game",
};
