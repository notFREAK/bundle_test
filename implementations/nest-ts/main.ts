import { Body, Controller, Get, Headers, HttpException, HttpStatus, Module, Post } from '@nestjs/common';
import { NestFactory } from '@nestjs/core';
import { randomBytes } from 'crypto';

type User = { username: string; email: string; password: string; role: string };
const users = new Map<string, User>();
const access = new Map<string, string>();
const refresh = new Map<string, string>();
let uptimeSeconds = 0;

const token = () => randomBytes(24).toString('hex');
const userByAuth = (authorization?: string) => {
  if (!authorization?.startsWith('Bearer ')) return null;
  const username = access.get(authorization.slice(7));
  return username ? users.get(username) ?? null : null;
};

@Controller('/api/v1')
class ApiController {
  @Post('/auth/register')
  register(@Body() body: any) {
    if (!body?.username || !body?.password) throw new HttpException({ error: { code: 'VALIDATION_ERROR' } }, HttpStatus.BAD_REQUEST);
    if (users.has(body.username)) throw new HttpException({ error: { code: 'CONFLICT' } }, HttpStatus.CONFLICT);
    users.set(body.username, { username: body.username, email: body.email ?? `${body.username}@example.local`, password: body.password, role: 'viewer' });
    return { status: 'registered' };
  }

  @Post('/auth/login')
  login(@Body() body: any) {
    const user = users.get(body?.username);
    if (!user || user.password !== body?.password) throw new HttpException({ error: { code: 'UNAUTHORIZED' } }, HttpStatus.UNAUTHORIZED);
    const accessToken = token();
    const refreshToken = token();
    access.set(accessToken, user.username);
    refresh.set(refreshToken, user.username);
    return { accessToken, refreshToken };
  }

  @Post('/auth/refresh')
  refreshToken(@Body() body: any) {
    const username = refresh.get(body?.refreshToken);
    if (!username) throw new HttpException({ error: { code: 'UNAUTHORIZED' } }, HttpStatus.UNAUTHORIZED);
    const accessToken = token();
    access.set(accessToken, username);
    return { accessToken, refreshToken: body.refreshToken };
  }

  @Post('/auth/logout')
  logout(@Body() body: any, @Headers('authorization') authorization?: string) {
    if (!userByAuth(authorization)) throw new HttpException({ error: { code: 'UNAUTHORIZED' } }, HttpStatus.UNAUTHORIZED);
    refresh.delete(body?.refreshToken);
    return { status: 'ok' };
  }

  @Get('/auth/me')
  me(@Headers('authorization') authorization?: string) {
    const user = userByAuth(authorization);
    if (!user) throw new HttpException({ error: { code: 'UNAUTHORIZED' } }, HttpStatus.UNAUTHORIZED);
    return { username: user.username, email: user.email, role: user.role };
  }

  @Get('/metrics/current')
  metrics(@Headers('authorization') authorization?: string) {
    if (!userByAuth(authorization)) throw new HttpException({ error: { code: 'UNAUTHORIZED' } }, HttpStatus.UNAUTHORIZED);
    uptimeSeconds += 1;
    return { temperatureC: 25, cpuLoadPercent: 10, ramLoadPercent: 20, uptimeSeconds, supplyVoltageV: 12, timestampUtc: new Date().toISOString() };
  }

  @Get('/gateway/status')
  status() { return { service: 'ok', opcua: 'simulated', cache: 'ready' }; }
}

@Module({ controllers: [ApiController] })
class AppModule {}

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  await app.listen(3000);
}
bootstrap();
