/*
 * 只给编辑器进程用的 bind() 替换（经 LD_PRELOAD 载入）：把绑定到通配地址的套接字改绑到本机回环地址。
 * Qt 的 vnc 平台在所有网络接口上监听、不要求认证，也没有选项改监听地址；改绑后只有本机能连上编辑器的画面和输入。
 * IPv4 的 0.0.0.0 改成 127.0.0.1；IPv6 的 :: 改成 ::ffff:127.0.0.1，双栈套接字仍收本机经 127.0.0.1 来的连接。
 */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <dlfcn.h>
#include <netinet/in.h>
#include <string.h>
#include <sys/socket.h>

int bind(int fd, const struct sockaddr *addr, socklen_t len) {
  int (*real_bind)(int, const struct sockaddr *, socklen_t) =
      (int (*)(int, const struct sockaddr *, socklen_t))dlsym(RTLD_NEXT, "bind");
  if (addr && addr->sa_family == AF_INET && len >= sizeof(struct sockaddr_in)) {
    struct sockaddr_in v4;
    memcpy(&v4, addr, sizeof v4);
    if (v4.sin_addr.s_addr == htonl(INADDR_ANY)) {
      v4.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
      return real_bind(fd, (const struct sockaddr *)&v4, sizeof v4);
    }
  }
  if (addr && addr->sa_family == AF_INET6 && len >= sizeof(struct sockaddr_in6)) {
    struct sockaddr_in6 v6;
    memcpy(&v6, addr, sizeof v6);
    if (IN6_IS_ADDR_UNSPECIFIED(&v6.sin6_addr)) {
      inet_pton(AF_INET6, "::ffff:127.0.0.1", &v6.sin6_addr);
      return real_bind(fd, (const struct sockaddr *)&v6, sizeof v6);
    }
  }
  return real_bind(fd, addr, len);
}
