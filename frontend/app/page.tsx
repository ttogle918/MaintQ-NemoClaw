import { redirect } from "next/navigation";
import { ROLE_HOME } from "@/lib/role";

/** 진입은 정비사 콘솔로. 역할은 라우트가 결정한다. */
export default function Page() {
  redirect(ROLE_HOME.technician);
}
