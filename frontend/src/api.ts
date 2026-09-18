let token = sessionStorage.getItem("projection-token") ?? "";
export const getToken = () => token;
export function setToken(value: string) {
  token = value;
  sessionStorage.setItem("projection-token", value);
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api/${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const body = await response.text();
    try {
      const detail = JSON.parse(body).detail;
      throw new Error(
        typeof detail === "string" ? detail : JSON.stringify(detail),
      );
    } catch (error) {
      if (error instanceof SyntaxError)
        throw new Error(`${response.status}: ${body}`);
      throw error;
    }
  }
  return response.json() as Promise<T>;
}
