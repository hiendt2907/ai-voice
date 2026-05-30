import { IsString, IsNumber, IsOptional, Min, Max, IsObject } from 'class-validator'

export class UpsertDoctorCheckDto {
  @IsString()
  baseUrl: string

  @IsOptional()
  @IsString()
  apiKey?: string

  @IsOptional()
  @IsObject()
  specialtyMapping?: Record<string, string>

  @IsOptional()
  @IsObject()
  slotMapping?: Record<string, string>

  @IsOptional()
  @IsString()
  bookingConfirmTemplate?: string

  @IsOptional()
  @IsNumber()
  @Min(0)
  @Max(5)
  retryCount?: number

  @IsOptional()
  @IsNumber()
  @Min(1000)
  @Max(30000)
  timeoutMs?: number
}
